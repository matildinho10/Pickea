"""
Prepara los datos del gráfico de unidades acumuladas del perfil.

El gráfico se dibuja en un SVG de 1000 x 1000 "unidades internas" que se estira
al tamaño real de la pantalla; por eso aquí todo se calcula entre 0 y 1000.
Los textos (ejes) van en HTML aparte para que no se deformen.
"""
import math

from django.utils import timezone
from django.utils.formats import date_format


def paso_redondo(rango, marcas=4):
    """Elige un paso 'bonito' (1, 2, 5, 10, 20, 50...) para las líneas del eje."""
    if rango <= 0:
        return 1
    bruto = rango / marcas
    potencia = 10 ** math.floor(math.log10(bruto))
    for m in (1, 2, 5, 10):
        if bruto <= m * potencia:
            return m * potencia
    return 10 * potencia


def preparar(serie):
    """
    serie = [(partido, acumulado), ...] en orden cronológico (de estadisticas.calcular).
    Devuelve None si no hay datos.
    """
    if not serie:
        return None
    valores = [0.0] + [v for _, v in serie]          # el gráfico parte en 0
    minimo, maximo = min(valores + [0]), max(valores + [0])
    paso = paso_redondo(maximo - minimo)
    abajo = math.floor(minimo / paso) * paso
    arriba = math.ceil(maximo / paso) * paso
    if arriba == abajo:
        arriba = abajo + paso

    n = len(valores)
    def x(i):
        return i / (n - 1) * 1000
    def y(v):
        return (arriba - v) / (arriba - abajo) * 1000

    puntos = [(round(x(i), 2), round(y(v), 2)) for i, v in enumerate(valores)]
    marcas = []
    v = abajo
    while v <= arriba + 1e-9:
        marcas.append({'valor': v, 'y_svg': y(v), 'y': y(v) / 10})   # y: en % para el HTML
        v += paso

    datos = [{'x': 0, 'y': puntos[0][1] / 10, 'partido': 'Inicio', 'fecha': '', 'g': 0, 'a': 0}]
    anterior = 0.0
    for i, (p, acumulado) in enumerate(serie, start=1):
        datos.append({
            'x': puntos[i][0] / 10, 'y': puntos[i][1] / 10,
            'partido': str(p),
            'fecha': date_format(timezone.localtime(p.inicio), 'j M Y'),
            'g': round(acumulado - anterior, 2),
            'a': round(acumulado, 2),
        })
        anterior = acumulado

    final = valores[-1]
    return {
        'puntos': ' '.join(f'{px},{py}' for px, py in puntos),
        'cero_y': round(y(0), 2),
        'marcas': marcas,
        'final': final,
        'final_x': puntos[-1][0] / 10,
        'final_y': puntos[-1][1] / 10,
        'n_partidos': len(serie),
        'datos': datos,
    }
