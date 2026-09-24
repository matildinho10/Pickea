"""
Estadísticas de cada usuario como tipster.

Solo cuentan las apuestas ya decididas (ganadas o perdidas). Las nulas (se
devolvió la apuesta) y las pendientes quedan fuera.

Fórmulas (s = unidades, o = cuota):
    g_i  = s*(o-1) si gana, -s si pierde          ROI = suma(g) / suma(s)
    G_m  = suma de g_i del partido m               S_m = unidades apostadas en m
    z    = suma(G_m) / raiz(suma(G_m^2))           p = 1 - Phi(z)
    n_ef = (suma S_m)^2 / suma(S_m^2)
    CLV  = o / cuota_cierre - 1, promedio ponderado por unidades
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import NormalDist

from .models import Apuesta, Opcion

MINIMO_PARTIDOS_EFECTIVOS = 30


@dataclass
class Estadisticas:
    usuario: object
    apuestas: int = 0
    unidades: float = 0.0          # suma(s)
    ganancia: float = 0.0          # suma(g)
    roi: float | None = None
    z: float | None = None
    p_valor: float | None = None
    partidos: int = 0              # partidos distintos
    partidos_efectivos: float = 0.0
    cuota_promedio: float | None = None
    clv: float | None = None
    # [(partido, ganancia acumulada después de ese partido), ...] para el gráfico
    serie: list = field(default_factory=list)

    @property
    def unidades_por_apuesta(self):
        return self.unidades / self.apuestas if self.apuestas else None

    @property
    def en_ranking(self):
        return self.partidos_efectivos >= MINIMO_PARTIDOS_EFECTIVOS


def _z(valores):
    """z = suma / raiz(suma de cuadrados). None si no hay datos o todo es 0."""
    denominador = math.sqrt(sum(v * v for v in valores))
    return sum(valores) / denominador if denominador > 0 else None


def _p(z):
    return None if z is None else 1 - NormalDist().cdf(z)


def apuestas_decididas(temporada=None):
    """Apuestas ganadas o perdidas, con todo lo necesario cargado en una sola consulta."""
    qs = (Apuesta.objects
          .filter(opcion__resultado__in=[Opcion.Resultado.GANADA, Opcion.Resultado.PERDIDA])
          .select_related('usuario', 'opcion__mercado__partido'))
    if temporada is not None:
        qs = qs.filter(opcion__mercado__partido__temporada=temporada)
    return qs


def calcular(usuario, apuestas):
    """Calcula todas las estadísticas de un usuario a partir de sus apuestas decididas."""
    e = Estadisticas(usuario=usuario)
    G = defaultdict(float)     # ganancia por partido
    S = defaultdict(float)     # unidades por partido
    partidos = {}
    suma_cuotas = clv_num = clv_uni = 0.0

    for a in apuestas:
        s, o, g = a.unidades, float(a.cuota), float(a.ganancia)
        p = a.opcion.mercado.partido
        partidos[p.pk] = p
        G[p.pk] += g
        S[p.pk] += s
        e.apuestas += 1
        e.unidades += s
        e.ganancia += g
        suma_cuotas += o
        if a.opcion.cuota_cierre:
            clv_num += s * (o / float(a.opcion.cuota_cierre) - 1)
            clv_uni += s

    if not e.apuestas:
        return e

    e.roi = e.ganancia / e.unidades
    e.z = _z(list(G.values()))
    e.p_valor = _p(e.z)
    e.partidos = len(G)
    e.partidos_efectivos = sum(S.values()) ** 2 / sum(v * v for v in S.values())
    e.cuota_promedio = suma_cuotas / e.apuestas
    e.clv = clv_num / clv_uni if clv_uni else None

    acumulado = 0.0
    for p in sorted(partidos.values(), key=lambda p: (p.inicio, p.pk)):
        acumulado += G[p.pk]
        e.serie.append((p, acumulado))
    return e


def estadisticas_usuario(usuario, temporada=None):
    return calcular(usuario, apuestas_decididas(temporada).filter(usuario=usuario))


def ranking(temporada=None):
    """
    Todos los usuarios con apuestas decididas, ordenados por z (mayor primero).
    Devuelve (en_ranking, bajo_minimo): los que tienen 30+ partidos efectivos y los demás.
    """
    por_usuario = defaultdict(list)
    for a in apuestas_decididas(temporada):
        por_usuario[a.usuario].append(a)
    todos = [calcular(u, lista) for u, lista in por_usuario.items()]
    todos.sort(key=lambda e: (e.z is None, -(e.z or 0)))
    return [e for e in todos if e.en_ranking], [e for e in todos if not e.en_ranking]
