"""
Filtros para mostrar números en las plantillas, p. ej. {{ e.roi|porcentaje }} -> "+7.8%".
Usamos el signo menos tipográfico (−) para que las columnas queden alineadas.
"""
import re

from django import template

register = template.Library()


@register.filter
def con_signo(valor, decimales=1):
    """12.345 -> '+12.3' ; -4 -> '−4.0' ; 0 -> '0.0'"""
    if valor is None:
        return '—'
    texto = f'{abs(valor):.{int(decimales)}f}'
    if float(texto) == 0:
        return texto
    return ('+' if valor > 0 else '−') + texto


@register.filter
def porcentaje(valor, decimales=1):
    """0.078 -> '+7.8%'"""
    return '—' if valor is None else con_signo(valor * 100, decimales) + '%'


@register.filter
def decimal(valor, decimales=2):
    """2.1436 -> '2.14' (siempre con punto, sin signo)."""
    return '—' if valor is None else f'{valor:.{int(decimales)}f}'


@register.filter
def probabilidad(p):
    """0.0123 -> '1.2%' ; 0.0004 -> 'menos de 0.1%'"""
    if p is None:
        return '—'
    return 'menos de 0.1%' if p < 0.001 else f'{p * 100:.1f}%'


@register.filter
def iniciales(nombre):
    """'la_cuota_justa' -> 'LC' ; 'goleador' -> 'GO'"""
    partes = [x for x in re.split(r'[_.\-+@\d]+', nombre) if x]
    if len(partes) >= 2:
        return (partes[0][0] + partes[1][0]).upper()
    return (partes[0] if partes else nombre)[:2].upper()


@register.filter
def pvalor(p):
    if p is None:
        return '—'
    return '<0.001' if p < 0.001 else f'{p:.3f}'


@register.filter
def tono(valor):
    """Clase CSS según el signo: verde si es positivo, rojo si es negativo."""
    if valor is None or abs(valor) < 1e-9:
        return ''
    return 'positivo' if valor > 0 else 'negativo'

