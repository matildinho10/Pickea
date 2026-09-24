"""
Respaldo diario automático sin tareas programadas (el plan gratis de
PythonAnywhere no las permite).

Después de responder una visita, si el último respaldo tiene más de 24 horas,
se crea uno nuevo. Para no revisar la carpeta en cada visita, se revisa como
máximo una vez por hora. Solo funciona en internet (RESPALDO_AUTOMATICO).
"""
import io
import logging
import time
from pathlib import Path

from django.conf import settings
from django.core.management import call_command

log = logging.getLogger(__name__)

UNA_HORA = 60 * 60
UN_DIA = 24 * UNA_HORA
_ultima_revision = 0.0


def revisar_respaldo(ahora=None):
    """Crea un respaldo si el más reciente tiene más de un día. Devuelve True si creó uno."""
    global _ultima_revision
    ahora = ahora if ahora is not None else time.time()
    if ahora - _ultima_revision < UNA_HORA:
        return False
    _ultima_revision = ahora

    carpeta = Path(settings.RESPALDOS_DIR)
    respaldos = sorted(carpeta.glob('pronostika_*.tar.gz')) if carpeta.exists() else []
    if respaldos and ahora - respaldos[-1].stat().st_mtime < UN_DIA:
        return False
    try:
        call_command('respaldar', stdout=io.StringIO())
        return True
    except Exception:
        # Un respaldo fallido nunca debe romper la página
        log.exception('No se pudo crear el respaldo automático')
        return False


class RespaldoDiarioMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        if settings.RESPALDO_AUTOMATICO:
            revisar_respaldo()
        return respuesta
