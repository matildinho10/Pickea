"""
Modelos de la base de datos.

Cada clase de este archivo es una tabla. Cada atributo (models.CharField, etc.)
es una columna. Django crea las tablas por nosotros con `migrate`.

Jerarquía:
    Temporada ─┐
    Equipo ────┴─> Partido ──> Mercado ──> Opcion <── Apuesta ──> Usuario
"""
import uuid
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone


def ruta_foto(usuario, nombre_original):
    """Nombre al azar para cada foto: evita choques y no revela el nombre del archivo original."""
    return f'fotos/{uuid.uuid4().hex}.jpg'


class Usuario(AbstractUser):
    """Usuario de la página. Hereda nombre, contraseña, email, etc. de Django."""

    foto = models.ImageField(upload_to=ruta_foto, blank=True)

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'

    def sigue_a(self, otro):
        return Seguimiento.objects.filter(seguidor=self, seguido=otro).exists()


class Seguimiento(models.Model):
    """'seguidor' sigue a 'seguido' (un tipster que le interesa)."""

    seguidor = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='seguimientos')
    seguido = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='seguidores')
    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['seguidor', 'seguido'], name='seguir_una_sola_vez'),
            models.CheckConstraint(condition=~models.Q(seguidor=models.F('seguido')), name='no_seguirse_a_si_mismo'),
        ]

    def __str__(self):
        return f'{self.seguidor} sigue a {self.seguido}'


class Temporada(models.Model):
    nombre = models.CharField(max_length=50)       # "Primera División 2026"
    anio = models.PositiveSmallIntegerField(unique=True)
    activa = models.BooleanField(default=False)    # la que se muestra en la pestaña "Temporada"

    class Meta:
        ordering = ['-anio']

    def __str__(self):
        return self.nombre


class Equipo(models.Model):
    nombre = models.CharField(max_length=60, unique=True)   # "Universidad de Chile"
    nombre_corto = models.CharField(max_length=30)          # "U. de Chile"

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre_corto


class Partido(models.Model):
    class Estado(models.TextChoices):
        PROGRAMADO = 'programado', 'Programado'
        EN_JUEGO = 'en_juego', 'En juego'
        FINALIZADO = 'finalizado', 'Finalizado'
        SUSPENDIDO = 'suspendido', 'Suspendido'

    temporada = models.ForeignKey(Temporada, on_delete=models.PROTECT, related_name='partidos')
    fecha_numero = models.PositiveSmallIntegerField('fecha')   # "Fecha 24"
    local = models.ForeignKey(Equipo, on_delete=models.PROTECT, related_name='partidos_local')
    visita = models.ForeignKey(Equipo, on_delete=models.PROTECT, related_name='partidos_visita')
    inicio = models.DateTimeField()     # a esta hora se cierran las apuestas
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PROGRAMADO)

    # Resultado (vacío hasta que termina el partido)
    goles_local = models.PositiveSmallIntegerField(null=True, blank=True)
    goles_visita = models.PositiveSmallIntegerField(null=True, blank=True)
    goles_local_ht = models.PositiveSmallIntegerField('goles local al descanso', null=True, blank=True)
    goles_visita_ht = models.PositiveSmallIntegerField('goles visita al descanso', null=True, blank=True)
    corners = models.PositiveSmallIntegerField('córners totales', null=True, blank=True)
    tarjetas = models.PositiveSmallIntegerField('tarjetas totales', null=True, blank=True)

    # Marca de que ya copiamos las cuotas de cierre (se hace una sola vez)
    cuotas_cierre_fijadas = models.BooleanField(default=False)

    class Meta:
        ordering = ['inicio']

    def __str__(self):
        return f'{self.local} vs {self.visita}'

    @property
    def acepta_apuestas(self):
        return self.estado == self.Estado.PROGRAMADO and timezone.now() < self.inicio

    def fijar_cuotas_cierre(self):
        """Copia la cuota vigente de cada opción como cuota de cierre (al iniciar el partido)."""
        if self.cuotas_cierre_fijadas:
            return
        with transaction.atomic():
            for opcion in Opcion.objects.filter(mercado__partido=self):
                opcion.cuota_cierre = opcion.cuota
                opcion.save(update_fields=['cuota_cierre'])
            self.cuotas_cierre_fijadas = True
            self.save(update_fields=['cuotas_cierre_fijadas'])

    def liquidar(self):
        """Marca cada opción como ganada/perdida/nula según el resultado cargado."""
        if self.goles_local is None or self.goles_visita is None:
            raise ValidationError('Falta cargar el resultado del partido.')
        with transaction.atomic():
            for mercado in self.mercados.prefetch_related('opciones'):
                for opcion in mercado.opciones.all():
                    opcion.resultado = resolver_opcion(self, mercado.tipo, opcion.codigo)
                    opcion.save(update_fields=['resultado'])
            self.estado = self.Estado.FINALIZADO
            self.save(update_fields=['estado'])


def fijar_cierres_pendientes():
    """Fija la cuota de cierre de los partidos que ya empezaron y aún no la tienen."""
    for p in Partido.objects.filter(inicio__lte=timezone.now(), cuotas_cierre_fijadas=False):
        p.fijar_cuotas_cierre()


# Catálogo de mercados: código -> (nombre visible, ¿es principal?, opciones)
# Las opciones son (código, etiqueta). "{local}" y "{visita}" se reemplazan por los equipos.
MERCADOS = {
    '1x2':   ('Resultado (1 X 2)', True,  [('1', 'Gana {local}'), ('X', 'Empate'), ('2', 'Gana {visita}')]),
    'ou25':  ('Goles 2.5',         True,  [('mas', 'Más de 2.5 goles'), ('menos', 'Menos de 2.5 goles')]),
    'dc':    ('Doble oportunidad', False, [('1X', '{local} o empate'), ('12', '{local} o {visita}'), ('X2', 'Empate o {visita}')]),
    'dnb':   ('Empate no válido',  False, [('1', 'Gana {local}'), ('2', 'Gana {visita}')]),
    'btts':  ('Ambos marcan',      False, [('si', 'Ambos marcan: Sí'), ('no', 'Ambos marcan: No')]),
    'ht1x2': ('Resultado al descanso', False, [('1', 'Descanso: {local}'), ('X', 'Descanso: empate'), ('2', 'Descanso: {visita}')]),
    'ou15':  ('Goles 1.5',         False, [('mas', 'Más de 1.5 goles'), ('menos', 'Menos de 1.5 goles')]),
    'ou35':  ('Goles 3.5',         False, [('mas', 'Más de 3.5 goles'), ('menos', 'Menos de 3.5 goles')]),
    'cor95': ('Córners 9.5',       False, [('mas', 'Más de 9.5 córners'), ('menos', 'Menos de 9.5 córners')]),
    'tar45': ('Tarjetas 4.5',      False, [('mas', 'Más de 4.5 tarjetas'), ('menos', 'Menos de 4.5 tarjetas')]),
}


def _signo(a, b):
    return '1' if a > b else '2' if b > a else 'X'


def _mas_menos(total, linea, codigo):
    if total is None:
        return Opcion.Resultado.NULA   # no se registró el dato: se devuelve la apuesta
    gana = total > linea if codigo == 'mas' else total < linea
    return Opcion.Resultado.GANADA if gana else Opcion.Resultado.PERDIDA


def resolver_opcion(p, tipo, codigo):
    """Decide si una opción ganó, perdió o es nula, mirando el marcador del partido."""
    R = Opcion.Resultado
    gl, gv = p.goles_local, p.goles_visita
    ok = lambda cond: R.GANADA if cond else R.PERDIDA

    if tipo == '1x2':
        return ok(_signo(gl, gv) == codigo)
    if tipo == 'dc':
        return ok(_signo(gl, gv) in codigo)
    if tipo == 'dnb':
        return R.NULA if gl == gv else ok(_signo(gl, gv) == codigo)
    if tipo == 'btts':
        ambos = gl > 0 and gv > 0
        return ok(ambos if codigo == 'si' else not ambos)
    if tipo == 'ht1x2':
        if p.goles_local_ht is None or p.goles_visita_ht is None:
            return R.NULA
        return ok(_signo(p.goles_local_ht, p.goles_visita_ht) == codigo)
    if tipo in ('ou15', 'ou25', 'ou35'):
        return _mas_menos(gl + gv, {'ou15': 1.5, 'ou25': 2.5, 'ou35': 3.5}[tipo], codigo)
    if tipo == 'cor95':
        return _mas_menos(p.corners, 9.5, codigo)
    if tipo == 'tar45':
        return _mas_menos(p.tarjetas, 4.5, codigo)
    raise ValueError(f'Mercado desconocido: {tipo}')


class Mercado(models.Model):
    TIPOS = [(k, v[0]) for k, v in MERCADOS.items()]

    partido = models.ForeignKey(Partido, on_delete=models.CASCADE, related_name='mercados')
    tipo = models.CharField(max_length=10, choices=TIPOS)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['partido', 'tipo'], name='un_mercado_por_tipo')]

    def __str__(self):
        return f'{self.partido} · {self.get_tipo_display()}'

    @property
    def es_principal(self):
        return MERCADOS[self.tipo][1]

    def suma_inversas(self, campo='cuota'):
        """B = suma de 1/cuota de todas las opciones. Si B = 1.05, el margen de la casa es 5%."""
        cuotas = [getattr(o, campo) for o in self.opciones.all()]
        if not cuotas or any(c is None for c in cuotas):
            return None
        return sum(Decimal(1) / c for c in cuotas)


class Opcion(models.Model):
    """Una opción apostable dentro de un mercado, p. ej. 'Empate' dentro de 1X2."""

    class Resultado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        GANADA = 'ganada', 'Ganada'
        PERDIDA = 'perdida', 'Perdida'
        NULA = 'nula', 'Nula (se devuelve)'

    mercado = models.ForeignKey(Mercado, on_delete=models.CASCADE, related_name='opciones')
    codigo = models.CharField(max_length=10)       # '1', 'X', 'mas', 'si', ...
    etiqueta = models.CharField(max_length=80)     # 'Gana Colo-Colo'
    orden = models.PositiveSmallIntegerField(default=0)
    cuota = models.DecimalField('cuota vigente', max_digits=6, decimal_places=2,
                                validators=[MinValueValidator(Decimal('1.01'))])
    cuota_cierre = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    resultado = models.CharField(max_length=10, choices=Resultado.choices, default=Resultado.PENDIENTE)

    class Meta:
        ordering = ['mercado', 'orden']
        verbose_name = 'opción'
        verbose_name_plural = 'opciones'
        constraints = [models.UniqueConstraint(fields=['mercado', 'codigo'], name='opcion_unica_en_mercado')]

    def __str__(self):
        return f'{self.etiqueta} @ {self.cuota}'

    @property
    def corto(self):
        """Texto corto para el botón de la cuota: '1', 'X', 'Más', 'Sí', '1X'..."""
        return {'mas': 'Más', 'menos': 'Menos', 'si': 'Sí', 'no': 'No'}.get(self.codigo, self.codigo)


class Apuesta(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='apuestas')
    opcion = models.ForeignKey(Opcion, on_delete=models.PROTECT, related_name='apuestas')
    unidades = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])

    # Todo lo siguiente se copia automáticamente al confirmar y NUNCA cambia después.
    cuota = models.DecimalField('cuota fijada', max_digits=6, decimal_places=2)
    # Cuotas de TODAS las opciones del mercado en ese momento, p. ej. {"1": "1.72", "X": "3.60", "2": "4.80"}
    cuotas_mercado = models.JSONField()
    # B = suma de 1/cuota del mercado en ese momento (B - 1 = margen de la casa)
    suma_inversas = models.DecimalField(max_digits=8, decimal_places=5)
    creada = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-creada']
        constraints = [
            models.CheckConstraint(condition=models.Q(unidades__gte=1, unidades__lte=10),
                                   name='unidades_entre_1_y_10'),
        ]

    def __str__(self):
        return f'{self.usuario} · {self.opcion.etiqueta} · {self.unidades} u @ {self.cuota}'

    @classmethod
    def confirmar(cls, usuario, opcion, unidades, ahora=None):
        """
        Única forma correcta de crear una apuesta: el usuario solo elige opción y unidades;
        la cuota la ponemos nosotros, tomando la vigente en este instante.
        """
        ahora = ahora or timezone.now()
        if not 1 <= int(unidades) <= 10:
            raise ValidationError('Las unidades deben estar entre 1 y 10.')
        with transaction.atomic():
            # Releemos la opción desde la base para usar la cuota más reciente
            opcion = Opcion.objects.select_related('mercado__partido').get(pk=opcion.pk)
            partido = opcion.mercado.partido
            if partido.estado != Partido.Estado.PROGRAMADO or ahora >= partido.inicio:
                raise ValidationError('Las apuestas para este partido ya están cerradas.')
            hermanas = list(opcion.mercado.opciones.all())
            return cls.objects.create(
                usuario=usuario,
                opcion=opcion,
                unidades=int(unidades),
                cuota=opcion.cuota,
                cuotas_mercado={o.codigo: str(o.cuota) for o in hermanas},
                suma_inversas=sum(Decimal(1) / o.cuota for o in hermanas),
                creada=ahora,
            )

    # ---- Valores derivados (se calculan, no se guardan) ----

    @property
    def partido(self):
        return self.opcion.mercado.partido

    @property
    def ganancia(self):
        """g_i = s*(o-1) si gana, -s si pierde, 0 si es nula. None si aún no se juega."""
        r = self.opcion.resultado
        if r == Opcion.Resultado.GANADA:
            return self.unidades * (self.cuota - 1)
        if r == Opcion.Resultado.PERDIDA:
            return Decimal(-self.unidades)
        if r == Opcion.Resultado.NULA:
            return Decimal(0)
        return None

    @property
    def ganancia_posible(self):
        """Lo que ganaría si acierta: s*(o-1)."""
        return self.unidades * (self.cuota - 1)

    @property
    def clv(self):
        """cuota apostada / cuota de cierre - 1."""
        cierre = self.opcion.cuota_cierre
        return self.cuota / cierre - 1 if cierre else None
