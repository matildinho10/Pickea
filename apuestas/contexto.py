"""Variables disponibles en TODAS las plantillas (nombre del sitio, etc.)."""
from django.conf import settings


def sitio(request):
    return {
        'NOMBRE_SITIO': settings.NOMBRE_SITIO,
        'DATOS_DE_EJEMPLO': settings.DATOS_DE_EJEMPLO,
    }
