"""
Vistas: cada función recibe una visita (request) y devuelve una página.
Buscan los datos y se los pasan a una plantilla HTML (carpeta templates/).
"""
import logging

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Prefetch, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .estadisticas import MINIMO_PARTIDOS_EFECTIVOS, estadisticas_usuario, ranking as calcular_ranking
from . import grafico
from .fotos import procesar_foto
from .correos import enviar_activacion, enviar_confirmacion, usuario_del_enlace
from .forms import CorreoForm, EntrarForm, FotoForm, RegistroForm, ReenviarForm
from .models import (MERCADOS, Apuesta, Mercado, Opcion, Partido, Seguimiento, Temporada, Usuario,
                     fijar_cierres_pendientes)

ORDEN_MERCADOS = list(MERCADOS)
log = logging.getLogger(__name__)


# Cómo se puede ordenar el ranking: nombre visible y criterio (mejor primero)
ORDENES_RANKING = {
    'pvalue': ('p-value', lambda e: (e.z is None, -(e.z or 0))),   # z alto = p-value bajo
    'ganancia': ('Ganancia', lambda e: -e.ganancia),
    'roi': ('ROI', lambda e: (e.roi is None, -(e.roi or 0))),
}


def periodo_elegido(request):
    """Temporada activa y si se pidió 'temporada' o 'historico' (?periodo=...)."""
    temporada = Temporada.objects.filter(activa=True).first()
    periodo = 'historico' if request.GET.get('periodo') == 'historico' or temporada is None else 'temporada'
    return temporada, periodo, (temporada if periodo == 'temporada' else None)


def ranking(request):
    temporada, periodo, filtro = periodo_elegido(request)
    orden = request.GET.get('orden') if request.GET.get('orden') in ORDENES_RANKING else 'pvalue'
    criterio = ORDENES_RANKING[orden][1]

    en_ranking, bajo_minimo = calcular_ranking(filtro)
    en_ranking.sort(key=criterio)
    bajo_minimo.sort(key=criterio)
    for puesto, e in enumerate(en_ranking, 1):
        e.puesto = puesto

    return render(request, 'apuestas/ranking.html', {
        'seccion': 'ranking',
        'temporada': temporada,
        'periodo': periodo,
        'orden': orden,
        'ordenes': [(clave, nombre) for clave, (nombre, _) in ORDENES_RANKING.items()],
        'en_ranking': en_ranking,
        'bajo_minimo': bajo_minimo,
        'ver_bajo_minimo': 'bajo' in request.GET,
        'minimo': MINIMO_PARTIDOS_EFECTIVOS,
    })


def partidos(request):
    fijar_cierres_pendientes()
    temporada = Temporada.objects.filter(activa=True).first()
    if temporada is None:
        return render(request, 'apuestas/partidos.html', {'seccion': 'partidos', 'lista': []})

    fechas = sorted(set(temporada.partidos.values_list('fecha_numero', flat=True)))
    # Por defecto: la primera fecha que todavía tiene partidos por jugar
    proxima = (temporada.partidos.filter(inicio__gt=timezone.now()).order_by('inicio')
               .values_list('fecha_numero', flat=True).first()) or (fechas[-1] if fechas else None)
    try:
        fecha = int(request.GET.get('fecha', proxima))
    except (TypeError, ValueError):
        fecha = proxima

    lista = list(temporada.partidos.filter(fecha_numero=fecha)
                 .select_related('local', 'visita')
                 .prefetch_related(Prefetch('mercados', queryset=Mercado.objects.prefetch_related('opciones'))))
    for p in lista:
        mercados = {m.tipo: m for m in p.mercados.all()}
        p.m_1x2 = mercados.pop('1x2', None)
        p.m_goles = mercados.pop('ou25', None)
        p.extras = sorted(mercados.values(), key=lambda m: ORDEN_MERCADOS.index(m.tipo))
        p.abierto = p.acepta_apuestas

    # Opción elegida desde la URL (?opcion=123), p. ej. al volver después de un error
    seleccion = None
    if request.GET.get('opcion', '').isdigit():
        o = (Opcion.objects.select_related('mercado__partido__local', 'mercado__partido__visita')
             .filter(pk=request.GET['opcion']).first())
        if o and o.mercado.partido.acepta_apuestas:
            seleccion = datos_opcion(o)

    mis_apuestas = []
    if request.user.is_authenticated:
        mis_apuestas = (Apuesta.objects.filter(usuario=request.user, opcion__mercado__partido__in=lista)
                        .select_related('opcion__mercado__partido__local', 'opcion__mercado__partido__visita'))

    anterior = max((f for f in fechas if f < fecha), default=None)
    siguiente = min((f for f in fechas if f > fecha), default=None)
    return render(request, 'apuestas/partidos.html', {
        'seccion': 'partidos',
        'temporada': temporada,
        'fecha': fecha,
        'anterior': anterior,
        'siguiente': siguiente,
        'lista': lista,
        'seleccion': seleccion,
        'mis_apuestas': mis_apuestas,
    })


def datos_opcion(o):
    """Lo que la boleta necesita mostrar de una opción."""
    p = o.mercado.partido
    return {
        'opcion': o.pk,
        'etiqueta': o.etiqueta,
        'partido': str(p),
        'cuando': timezone.localtime(p.inicio).strftime('%d/%m · %H:%M'),
        'cuota': str(o.cuota),
    }


@login_required
@require_POST
def apostar(request):
    """
    Recibe SOLO la opción y las unidades. La cuota la toma el servidor en este
    instante (Apuesta.confirmar); cualquier cuota que envíe el navegador se ignora.
    """
    opcion = get_object_or_404(Opcion, pk=request.POST.get('opcion'))
    fecha = opcion.mercado.partido.fecha_numero
    volver = reverse('partidos') + f'?fecha={fecha}'
    try:
        unidades = int(request.POST.get('unidades', ''))
        apuesta = Apuesta.confirmar(request.user, opcion, unidades)
    except (ValueError, ValidationError) as e:
        mensaje = e.messages[0] if isinstance(e, ValidationError) else 'Las unidades deben estar entre 1 y 10.'
        messages.error(request, mensaje)
        return redirect(volver + f'&opcion={opcion.pk}')

    texto = (f'Apuesta registrada: {apuesta.opcion.etiqueta}, {apuesta.unidades} u a cuota {apuesta.cuota}. '
             'La cuota ya no cambia aunque el mercado se mueva.')
    if request.POST.get('cuota_vista') and request.POST['cuota_vista'] != str(apuesta.cuota):
        texto = (f'Ojo: la cuota cambió de {request.POST["cuota_vista"]} a {apuesta.cuota} justo antes '
                 f'de confirmar. ') + texto
    messages.success(request, texto)
    return redirect(volver)


class GrupoPartido:
    """Las apuestas de un usuario en un mismo partido, con sus totales."""

    def __init__(self, partido, apuestas):
        self.partido = partido
        self.apuestas = apuestas
        self.unidades = sum(a.unidades for a in apuestas)
        ganancias = [a.ganancia for a in apuestas if a.ganancia is not None]
        self.ganancia = sum(ganancias) if ganancias else None
        self.ganancia_posible = sum(a.ganancia_posible for a in apuestas)


def agrupar_por_partido(apuestas):
    """Convierte una lista de apuestas en grupos por partido, respetando el orden de llegada."""
    grupos = {}
    for a in apuestas:
        grupos.setdefault(a.partido.pk, (a.partido, []))[1].append(a)
    return [GrupoPartido(p, lista) for p, lista in grupos.values()]


@login_required
def mis_apuestas(request):
    vista = 'historial' if request.GET.get('vista') == 'historial' else 'activas'
    mias = (Apuesta.objects.filter(usuario=request.user)
            .select_related('opcion__mercado__partido__local', 'opcion__mercado__partido__visita'))
    activas = mias.filter(opcion__resultado=Opcion.Resultado.PENDIENTE)
    historial = mias.exclude(opcion__resultado=Opcion.Resultado.PENDIENTE)

    pagina = None
    if vista == 'activas':
        # Las más próximas primero
        grupos = agrupar_por_partido(activas.order_by('opcion__mercado__partido__inicio', 'creada'))
    else:
        # Paginamos por partido (15 por página) para no cortar un partido entre dos páginas
        partidos = (Partido.objects.filter(mercados__opciones__apuestas__in=historial)
                    .distinct().order_by('-inicio', '-pk'))
        pagina = Paginator(partidos, 15).get_page(request.GET.get('pagina'))
        grupos = agrupar_por_partido(historial.filter(opcion__mercado__partido__in=list(pagina))
                                     .order_by('-opcion__mercado__partido__inicio', 'creada'))

    return render(request, 'apuestas/mis_apuestas.html', {
        'seccion': 'mis_apuestas',
        'vista': vista,
        'grupos': grupos,
        'pagina': pagina,
        'n_activas': activas.count(),
        'unidades_en_juego': activas.aggregate(total=Sum('unidades'))['total'] or 0,
        'stats': estadisticas_usuario(request.user),
    })


# Qué decirle a alguien que llegó a "Entrar" porque intentó usar algo que requiere sesión
MOTIVOS_PARA_ENTRAR = [
    ('/mis-apuestas/', 'Inicia sesión para ver tus apuestas.'),
    ('/mi-perfil/', 'Inicia sesión para ver tu perfil.'),
    ('/cuenta/', 'Inicia sesión para editar tu perfil.'),
    ('/partidos/', 'Inicia sesión para apostar.'),
    ('/siguiendo/', 'Inicia sesión para ver a los tipsters que sigues.'),
    ('/apostar/', 'Inicia sesión para apostar.'),
    ('/u/', 'Inicia sesión para seguir a otros tipsters.'),
]


def destino_seguro(request):
    """La página a la que quería ir (?next=...), solo si es de este mismo sitio."""
    destino = request.POST.get('next') or request.GET.get('next') or ''
    if url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()},
                                       require_https=request.is_secure()):
        return destino
    return ''


def motivo_para_entrar(destino):
    return next((texto for inicio, texto in MOTIVOS_PARA_ENTRAR if destino.startswith(inicio)), '')


class EntrarView(auth_views.LoginView):
    template_name = 'apuestas/entrar.html'
    form_class = EntrarForm

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['motivo'] = motivo_para_entrar(destino_seguro(self.request))
        return contexto


@login_required
def mi_perfil(request):
    """'Mi perfil' en la barra: sirve también sin sesión (primero te pide entrar)."""
    return redirect('perfil', username=request.user.username)


def registro(request):
    """Crea la cuenta desactivada y envía el correo con el enlace para activarla."""
    destino = destino_seguro(request)
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            usuario = form.save(commit=False)
            usuario.is_active = False          # se activa con el enlace del correo
            usuario.save()
            try:
                enviar_activacion(request, usuario)
            except Exception:
                log.exception('No se pudo enviar un correo')   # queda en el registro de errores
                usuario.delete()               # así puede volver a intentarlo con el mismo nombre
                form.add_error(None, 'No pudimos enviar el correo de activación. Intenta de nuevo en unos minutos.')
            else:
                return render(request, 'apuestas/aviso.html', {
                    'titulo': 'Revisa tu correo',
                    'mensaje': f'Te enviamos un enlace a {usuario.email} para activar tu cuenta. '
                               'Si no lo ves en unos minutos, revisa la carpeta de spam.',
                    'reenviar': True,
                })
    else:
        form = RegistroForm()
    return render(request, 'apuestas/registro.html', {'form': form, 'next': destino})


def activar(request, uidb64, codigo):
    """Enlace del correo de registro: activa la cuenta y deja la sesión iniciada."""
    usuario = usuario_del_enlace(uidb64, codigo)
    if usuario is None:
        return render(request, 'apuestas/aviso.html', {
            'titulo': 'Este enlace ya no sirve',
            'mensaje': 'Puede que ya lo hayas usado (en ese caso tu cuenta ya está activa y solo tienes que entrar) '
                       'o que haya vencido: los enlaces duran 3 días.',
            'reenviar': True, 'entrar': True,
        }, status=400)
    usuario.is_active = True
    usuario.email_verificado = True
    usuario.save(update_fields=['is_active', 'email_verificado'])
    login(request, usuario)
    messages.success(request, f'¡Cuenta activada! Bienvenido, @{usuario.username}. Ya puedes apostar.')
    return redirect('partidos')


def reenviar_activacion(request):
    form = ReenviarForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        usuario = Usuario.objects.filter(email__iexact=form.cleaned_data['email'], is_active=False).first()
        if usuario:
            try:
                enviar_activacion(request, usuario)
            except Exception:
                log.exception('No se pudo enviar un correo')   # queda en el registro de errores
                form.add_error(None, 'No pudimos enviar el correo. Intenta de nuevo en unos minutos.')
                return render(request, 'apuestas/reenviar.html', {'form': form})
        # Mismo mensaje exista o no la cuenta: así nadie puede averiguar qué correos están registrados
        return render(request, 'apuestas/aviso.html', {
            'titulo': 'Revisa tu correo',
            'mensaje': 'Si hay una cuenta sin activar con ese correo, te enviamos un nuevo enlace. '
                       'Revisa también la carpeta de spam.',
            'entrar': True,
        })
    return render(request, 'apuestas/reenviar.html', {'form': form})


def confirmar_correo(request, uidb64, codigo):
    """Enlace del correo que se envía al agregar o cambiar el correo en 'Editar perfil'."""
    usuario = usuario_del_enlace(uidb64, codigo)
    if usuario is None:
        return render(request, 'apuestas/aviso.html', {
            'titulo': 'Este enlace ya no sirve',
            'mensaje': 'Puede que ya lo hayas usado o que haya vencido. Desde "Editar perfil" puedes pedir uno nuevo.',
        }, status=400)
    usuario.email_verificado = True
    usuario.save(update_fields=['email_verificado'])
    messages.success(request, f'¡Listo! Confirmamos tu correo {usuario.email}.')
    return redirect('cuenta' if request.user == usuario else 'entrar')


class CambiarClaveView(auth_views.PasswordChangeView):
    template_name = 'apuestas/cambiar_clave.html'

    def get_success_url(self):
        messages.success(self.request, 'Cambiamos tu contraseña.')
        return reverse('cuenta')


def ultimas_decididas(usuario, temporada=None, partidos=8):
    """
    Apuestas ya decididas de los últimos partidos de un usuario, agrupadas por partido.
    No se muestran las activas, para que nadie copie picks que todavía están abiertos.
    """
    decididas = (Apuesta.objects.filter(usuario=usuario)
                 .exclude(opcion__resultado=Opcion.Resultado.PENDIENTE)
                 .select_related('opcion__mercado__partido__local', 'opcion__mercado__partido__visita'))
    if temporada:
        decididas = decididas.filter(opcion__mercado__partido__temporada=temporada)
    ultimos = list(Partido.objects.filter(mercados__opciones__apuestas__in=decididas)
                   .distinct().order_by('-inicio', '-pk')[:partidos])
    return agrupar_por_partido(decididas.filter(opcion__mercado__partido__in=ultimos)
                               .order_by('-opcion__mercado__partido__inicio', 'creada'))


def perfil(request, username):
    usuario = get_object_or_404(Usuario, username=username)
    temporada, periodo, filtro = periodo_elegido(request)
    stats = estadisticas_usuario(usuario, filtro)

    # Puesto en el ranking de la temporada (solo si llega al mínimo)
    puesto = None
    if temporada and stats.en_ranking:
        en_ranking, _ = calcular_ranking(temporada)
        puesto = next((i for i, e in enumerate(en_ranking, 1) if e.usuario == usuario), None)

    grupos = ultimas_decididas(usuario, filtro, partidos=8)

    return render(request, 'apuestas/perfil.html', {
        'seccion': 'perfil' if request.user == usuario else None,
        'perfil_usuario': usuario,
        'es_mio': request.user == usuario,
        'temporada': temporada,
        'periodo': periodo,
        'stats': stats,
        'puesto': puesto,
        'minimo': MINIMO_PARTIDOS_EFECTIVOS,
        'grafico': grafico.preparar(stats.serie),
        'grupos': grupos,
        'n_seguidores': usuario.seguidores.count(),
        'n_siguiendo': usuario.seguimientos.count(),
        'lo_sigo': request.user.is_authenticated and request.user.sigue_a(usuario),
    })


@login_required
@require_POST
def seguir(request, username):
    """Botón Seguir / Dejar de seguir (si ya lo sigues, lo deja de seguir)."""
    usuario = get_object_or_404(Usuario, username=username)
    if usuario != request.user:
        seguimiento, creado = Seguimiento.objects.get_or_create(seguidor=request.user, seguido=usuario)
        if not creado:
            seguimiento.delete()
    return redirect(destino_seguro(request) or reverse('perfil', args=[usuario.username]))


@login_required
def siguiendo(request):
    """Los tipsters que sigues: sus números y sus últimas apuestas decididas."""
    temporada, periodo, filtro = periodo_elegido(request)
    tipsters = []
    for usuario in Usuario.objects.filter(seguidores__seguidor=request.user).order_by('username'):
        stats = estadisticas_usuario(usuario, filtro)
        stats.grupos = ultimas_decididas(usuario, filtro, partidos=3)
        tipsters.append(stats)
    tipsters.sort(key=ORDENES_RANKING['pvalue'][1])
    return render(request, 'apuestas/siguiendo.html', {
        'seccion': 'siguiendo',
        'temporada': temporada,
        'periodo': periodo,
        'tipsters': tipsters,
        'minimo': MINIMO_PARTIDOS_EFECTIVOS,
    })


@login_required
def borrar_cuenta(request):
    """Borra la cuenta y todo lo asociado (apuestas, seguimientos, foto). Pide la contraseña."""
    error = ''
    if request.method == 'POST':
        if request.user.check_password(request.POST.get('password', '')):
            usuario = request.user
            if usuario.foto:
                usuario.foto.delete(save=False)
            logout(request)
            usuario.delete()   # las apuestas y seguimientos se borran en cascada
            return render(request, 'apuestas/aviso.html', {
                'titulo': 'Cuenta borrada',
                'mensaje': 'Borramos tu cuenta, tus apuestas y tu foto. Las copias de seguridad '
                           'se eliminan solas en un máximo de 14 días. ¡Gracias por haber probado Pronostika!',
            })
        error = 'La contraseña no es correcta.'
    return render(request, 'apuestas/borrar_cuenta.html', {'seccion': 'perfil', 'error': error})


def terminos(request):
    return render(request, 'apuestas/terminos.html')


def privacidad(request):
    return render(request, 'apuestas/privacidad.html')


@login_required
def cuenta(request):
    """Editar tu perfil: foto, correo y contraseña."""
    form = FotoForm()
    form_correo = CorreoForm(usuario=request.user, initial={'email': request.user.email})
    if request.method == 'POST' and request.POST.get('accion') == 'correo':
        form_correo = CorreoForm(request.POST, usuario=request.user)
        if form_correo.is_valid():
            request.user.email = form_correo.cleaned_data['email']
            request.user.email_verificado = False
            request.user.save(update_fields=['email', 'email_verificado'])
            try:
                enviar_confirmacion(request, request.user)
            except Exception:
                log.exception('No se pudo enviar un correo')   # queda en el registro de errores
                messages.error(request, 'Guardamos tu correo, pero no pudimos enviar la confirmación. '
                                        'Intenta de nuevo en unos minutos.')
            else:
                messages.success(request, f'Te enviamos un enlace a {request.user.email} para confirmarlo.')
            return redirect('cuenta')
    elif request.method == 'POST':
        if 'quitar' in request.POST:
            request.user.foto.delete(save=True)   # borra el archivo y deja el campo vacío
            messages.success(request, 'Quitamos tu foto. Ahora se muestran tus iniciales.')
            return redirect('cuenta')

        form = FotoForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                nueva = procesar_foto(form.cleaned_data['foto'])
            except Exception:
                form.add_error('foto', 'No pudimos leer esa imagen. Prueba con otra.')
            else:
                anterior = request.user.foto.name
                request.user.foto.save('foto.jpg', nueva, save=True)
                if anterior:
                    request.user.foto.storage.delete(anterior)   # no dejar fotos viejas ocupando espacio
                messages.success(request, '¡Foto actualizada!')
                return redirect('perfil', username=request.user.username)

    return render(request, 'apuestas/cuenta.html', {'seccion': 'perfil', 'form': form, 'form_correo': form_correo})


def como_funciona(request):
    return render(request, 'apuestas/como_funciona.html', {'seccion': 'guia'})
