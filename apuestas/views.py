"""
Vistas: cada función recibe una visita (request) y devuelve una página.
Buscan los datos y se los pasan a una plantilla HTML (carpeta templates/).
"""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Prefetch, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .estadisticas import MINIMO_PARTIDOS_EFECTIVOS, estadisticas_usuario, ranking as calcular_ranking
from . import grafico
from .forms import RegistroForm
from .models import MERCADOS, Apuesta, Mercado, Opcion, Partido, Temporada, Usuario, fijar_cierres_pendientes

ORDEN_MERCADOS = list(MERCADOS)


def ranking(request):
    temporada = Temporada.objects.filter(activa=True).first()
    periodo = 'historico' if request.GET.get('periodo') == 'historico' or temporada is None else 'temporada'
    en_ranking, bajo_minimo = calcular_ranking(temporada if periodo == 'temporada' else None)
    return render(request, 'apuestas/ranking.html', {
        'seccion': 'ranking',
        'temporada': temporada,
        'periodo': periodo,
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


def registro(request):
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            login(request, usuario)
            messages.success(request, f'¡Bienvenido, @{usuario.username}! Ya puedes apostar.')
            return redirect('partidos')
    else:
        form = RegistroForm()
    return render(request, 'apuestas/registro.html', {'form': form})


def perfil(request, username):
    usuario = get_object_or_404(Usuario, username=username)
    temporada = Temporada.objects.filter(activa=True).first()
    periodo = 'historico' if request.GET.get('periodo') == 'historico' or temporada is None else 'temporada'
    filtro = temporada if periodo == 'temporada' else None
    stats = estadisticas_usuario(usuario, filtro)

    # Puesto en el ranking de la temporada (solo si llega al mínimo)
    puesto = None
    if temporada and stats.en_ranking:
        en_ranking, _ = calcular_ranking(temporada)
        puesto = next((i for i, e in enumerate(en_ranking, 1) if e.usuario == usuario), None)

    # Últimas apuestas decididas (no se muestran las activas para que nadie copie picks abiertos)
    decididas = (Apuesta.objects.filter(usuario=usuario)
                 .exclude(opcion__resultado=Opcion.Resultado.PENDIENTE)
                 .select_related('opcion__mercado__partido__local', 'opcion__mercado__partido__visita'))
    if filtro:
        decididas = decididas.filter(opcion__mercado__partido__temporada=filtro)
    ultimos = list(Partido.objects.filter(mercados__opciones__apuestas__in=decididas)
                   .distinct().order_by('-inicio', '-pk')[:8])
    grupos = agrupar_por_partido(decididas.filter(opcion__mercado__partido__in=ultimos)
                                 .order_by('-opcion__mercado__partido__inicio', 'creada'))

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
    })
