"""
Carga datos de EJEMPLO: equipos de la Primera División, 23 fechas jugadas con
resultados y apuestas de usuarios de prueba, y las Fechas 24 y 25 por jugar.

Las fechas se calculan desde HOY: la Fecha 24 es el próximo fin de semana, así
que siempre hay partidos abiertos para apostar justo después de cargar.

Uso:  python manage.py cargar_ejemplo          (borra y vuelve a crear todo)
      python manage.py cargar_ejemplo --semilla 7   (otros datos al azar)
"""
import math
import random
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apuestas.models import MERCADOS, Apuesta, Equipo, Mercado, Opcion, Partido, Temporada, Usuario

TZ = ZoneInfo('America/Santiago')

# (nombre, nombre corto, fuerza de ataque, fuerza de defensa) -> inventadas
EQUIPOS = [
    ('Colo-Colo', 'Colo-Colo', 1.30, 0.80),
    ('Universidad de Chile', 'U. de Chile', 1.30, 0.78),
    ('Universidad Católica', 'U. Católica', 1.20, 0.90),
    ('Coquimbo Unido', 'Coquimbo Unido', 1.10, 0.85),
    ('Palestino', 'Palestino', 1.05, 0.95),
    ('Huachipato', 'Huachipato', 1.00, 1.00),
    ('Audax Italiano', 'Audax Italiano', 1.00, 1.05),
    ("O'Higgins", "O'Higgins", 0.95, 1.00),
    ('Everton', 'Everton', 0.90, 1.05),
    ('Unión La Calera', 'Unión La Calera', 0.90, 1.10),
    ('Ñublense', 'Ñublense', 0.90, 1.10),
    ('Cobreloa', 'Cobreloa', 0.85, 1.15),
    ('Deportes Iquique', 'D. Iquique', 0.90, 1.15),
    ('Deportes La Serena', 'D. La Serena', 0.85, 1.20),
    ('Deportes Limache', 'D. Limache', 0.80, 1.20),
    ('Universidad de Concepción', 'U. de Concepción', 0.80, 1.25),
]

# Partidos de la Fecha 24 (por jugar), igual a la maqueta
FECHA_24 = [
    ('Palestino', 'Huachipato'),
    ('Cobreloa', 'Universidad Católica'),
    ('Colo-Colo', 'Everton'),
    ('Ñublense', "O'Higgins"),
    ('Deportes Iquique', 'Deportes La Serena'),
    ('Universidad de Chile', 'Audax Italiano'),
    ('Coquimbo Unido', 'Unión La Calera'),
    ('Deportes Limache', 'Universidad de Concepción'),
]

# Horarios de una fecha: (día desde el viernes, hora, minuto)
HORARIOS = [(0, 20, 0), (1, 12, 30), (1, 15, 0), (1, 17, 30), (1, 20, 0), (2, 12, 30), (2, 15, 0), (2, 18, 0)]


def viernes_de_la_fecha_24():
    """El próximo viernes a partir de mañana (así la Fecha 24 nunca empezó todavía)."""
    manana = timezone.localdate() + timedelta(days=1)
    return manana + timedelta(days=(4 - manana.weekday()) % 7)   # 4 = viernes

# (usuario, habilidad 0..1, probabilidad de apostar en un partido)
USUARIOS = [
    ('goleador_datos', 0.55, 0.9), ('lacuotajusta', 0.45, 0.8), ('analisis_ohiggins', 0.40, 0.7),
    ('picks_del_sur', 0.35, 0.5), ('tercer_tiempo', 0.20, 0.95), ('xg_chile', 0.30, 0.35),
    ('banca_fria', 0.05, 0.6), ('el_profe_ricky', 0.0, 0.5), ('novato_2026', 0.0, 0.1),
]


# ---------- Probabilidades con un modelo de Poisson simple ----------

def poisson(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def probs_marcador(lam_l, lam_v, maximo=10):
    return {(i, j): poisson(i, lam_l) * poisson(j, lam_v)
            for i in range(maximo + 1) for j in range(maximo + 1)}


def prob_mas(total_lam, linea):
    return 1 - sum(poisson(k, total_lam) for k in range(int(linea) + 1))


def probabilidades(lam_l, lam_v):
    """Probabilidad real de cada opción de cada mercado."""
    g = probs_marcador(lam_l, lam_v)
    h = probs_marcador(lam_l * 0.45, lam_v * 0.45)   # ~45% de los goles llegan antes del descanso
    p1 = sum(p for (i, j), p in g.items() if i > j)
    px = sum(p for (i, j), p in g.items() if i == j)
    p2 = 1 - p1 - px
    btts = sum(p for (i, j), p in g.items() if i > 0 and j > 0)
    h1 = sum(p for (i, j), p in h.items() if i > j)
    hx = sum(p for (i, j), p in h.items() if i == j)
    tot = lam_l + lam_v
    o15, o25, o35 = prob_mas(tot, 1.5), prob_mas(tot, 2.5), prob_mas(tot, 3.5)
    oc, ot = prob_mas(9.8, 9.5), prob_mas(4.6, 4.5)
    return {
        '1x2': {'1': p1, 'X': px, '2': p2},
        'ou25': {'mas': o25, 'menos': 1 - o25},
        'dc': {'1X': p1 + px, '12': p1 + p2, 'X2': px + p2},
        'dnb': {'1': p1 / (p1 + p2), '2': p2 / (p1 + p2)},
        'btts': {'si': btts, 'no': 1 - btts},
        'ht1x2': {'1': h1, 'X': hx, '2': 1 - h1 - hx},
        'ou15': {'mas': o15, 'menos': 1 - o15},
        'ou35': {'mas': o35, 'menos': 1 - o35},
        'cor95': {'mas': oc, 'menos': 1 - oc},
        'tar45': {'mas': ot, 'menos': 1 - ot},
    }


def a_cuotas(probs, margen, ruido, rng):
    """Convierte probabilidades en cuotas con margen de la casa y un error de estimación."""
    ruidosas = {k: max(0.02, p * math.exp(rng.gauss(0, ruido))) for k, p in probs.items()}
    s = sum(ruidosas.values())
    doble = len(probs) == 3 and all(len(k) == 2 for k in probs)   # doble oportunidad suma 2
    objetivo = 2 if doble else 1
    return {k: Decimal(str(max(1.01, round(1 / (p / s * objetivo * margen), 2))))
            for k, p in ruidosas.items()}


class Command(BaseCommand):
    help = 'Borra los datos y carga una temporada de ejemplo.'

    def add_arguments(self, parser):
        parser.add_argument('--semilla', type=int, default=2,
                            help='Cambia la semilla para generar otros datos al azar.')

    @transaction.atomic
    def handle(self, *args, **opts):
        rng = random.Random(opts['semilla'])   # misma semilla = mismos datos

        Apuesta.objects.all().delete()
        Partido.objects.all().delete()
        Equipo.objects.all().delete()
        Temporada.objects.all().delete()
        Usuario.objects.filter(is_staff=False).delete()

        viernes_24 = viernes_de_la_fecha_24()
        anio = viernes_24.year
        temporada = Temporada.objects.create(nombre=f'Primera División {anio}', anio=anio, activa=True)
        equipos = {n: Equipo.objects.create(nombre=n, nombre_corto=c) for n, c, *_ in EQUIPOS}
        fuerza = {n: (a, d) for n, _, a, d in EQUIPOS}
        usuarios = []
        for nombre, habilidad, frecuencia in USUARIOS:
            u = Usuario.objects.create_user(nombre, password='demo12345')
            usuarios.append((u, habilidad, frecuencia))

        # Calendario "todos contra todos" (método del círculo), ida y vuelta
        nombres = [e[0] for e in EQUIPOS]
        rng.shuffle(nombres)
        fechas, rot = [], nombres[:]
        for r in range(15):
            pares = [(rot[i], rot[-1 - i]) for i in range(8)]
            fechas.append([(a, b) if r % 2 == 0 else (b, a) for a, b in pares])
            rot = [rot[0]] + [rot[-1]] + rot[1:-1]
        fechas += [[(b, a) for a, b in f] for f in fechas]

        def horarios(num):
            """Hora de inicio de cada partido de la fecha `num` (una fecha por semana)."""
            viernes = viernes_24 + timedelta(weeks=num - 24)
            return [datetime.combine(viernes + timedelta(days=dia), time(hh, mm), tzinfo=TZ)
                    for dia, hh, mm in HORARIOS]

        n_apuestas = 0
        for num in range(1, 24):   # fechas ya jugadas
            for (local, visita), inicio in zip(fechas[num - 1], horarios(num)):
                p, lams = self.crear_partido(temporada, num, equipos, fuerza, local, visita, inicio, rng)
                n_apuestas += self.simular_apuestas(p, usuarios, rng)
                self.cerrar_y_jugar(p, lams, rng)

        for num, pares in ((24, FECHA_24), (25, fechas[24])):   # fechas por jugar
            for (local, visita), inicio in zip(pares, horarios(num)):
                self.crear_partido(temporada, num, equipos, fuerza, local, visita, inicio, rng)

        self.stdout.write(self.style.SUCCESS(
            f'Listo: {len(equipos)} equipos, {Partido.objects.count()} partidos, '
            f'{Opcion.objects.count()} opciones con cuota, {len(usuarios)} usuarios, {n_apuestas} apuestas.'))
        self.stdout.write('Usuarios de prueba: contraseña "demo12345".')

    def crear_partido(self, temporada, num, equipos, fuerza, local, visita, inicio, rng):
        (al, dl), (av, dv) = fuerza[local], fuerza[visita]
        lams = (1.35 * al * dv * 1.1, 1.35 * av * dl / 1.1)   # ventaja de local ~10%
        p = Partido.objects.create(temporada=temporada, fecha_numero=num, inicio=inicio,
                                   local=equipos[local], visita=equipos[visita])
        p.probs = probabilidades(*lams)   # probabilidades "reales" (solo en memoria, para simular)
        for tipo, probs in p.probs.items():
            nombre, principal, opciones = MERCADOS[tipo]
            cuotas = a_cuotas(probs, 1.05 if principal else 1.07, 0.08, rng)   # apertura: más error
            m = Mercado.objects.create(partido=p, tipo=tipo)
            for orden, (codigo, etiqueta) in enumerate(opciones):
                Opcion.objects.create(mercado=m, codigo=codigo, orden=orden, cuota=cuotas[codigo],
                                      etiqueta=etiqueta.format(local=p.local, visita=p.visita))
        return p, lams

    def simular_apuestas(self, p, usuarios, rng):
        opciones = list(Opcion.objects.filter(mercado__partido=p).select_related('mercado'))
        principales = [o for o in opciones if o.mercado.es_principal]
        n = 0
        for u, habilidad, frecuencia in usuarios:
            if rng.random() > frecuencia:
                continue
            for _ in range(rng.choice([1, 1, 1, 2, 2, 3])):
                pool = principales if rng.random() < 0.7 else opciones
                if rng.random() < habilidad:   # el hábil busca la opción con más valor esperado
                    o = max(pool, key=lambda o: float(o.cuota) * p.probs[o.mercado.tipo][o.codigo])
                else:
                    o = rng.choice(pool)
                horas_antes = rng.uniform(0.5, 72)
                Apuesta.confirmar(u, o, rng.randint(1, 10), ahora=p.inicio - timedelta(hours=horas_antes))
                n += 1
        return n

    def cerrar_y_jugar(self, p, lams, rng):
        # Las cuotas se mueven hacia el valor real antes del inicio (el mercado "aprende")
        for m in p.mercados.prefetch_related('opciones'):
            principal = m.es_principal
            cierre = a_cuotas(p.probs[m.tipo], 1.04 if principal else 1.06, 0.03, rng)
            for o in m.opciones.all():
                o.cuota = cierre[o.codigo]
                o.save(update_fields=['cuota'])
        p.fijar_cuotas_cierre()

        def goles(lam):   # muestra de una Poisson
            k, t = 0, rng.random()
            acumulado = poisson(0, lam)
            while t > acumulado:
                k += 1
                acumulado += poisson(k, lam)
            return k
        p.goles_local_ht, p.goles_visita_ht = goles(lams[0] * 0.45), goles(lams[1] * 0.45)
        p.goles_local = p.goles_local_ht + goles(lams[0] * 0.55)
        p.goles_visita = p.goles_visita_ht + goles(lams[1] * 0.55)
        p.corners, p.tarjetas = goles(9.8), goles(4.6)
        p.save()
        p.liquidar()
