"""
Fija la cuota de cierre de los partidos que ya empezaron.

Uso:  python manage.py cerrar_partidos
Más adelante, cuando las cuotas vengan de la API, lo correremos automáticamente
cada pocos minutos. Por ahora también se ejecuta al abrir la página de partidos.
"""
from django.core.management.base import BaseCommand

from apuestas.models import fijar_cierres_pendientes


class Command(BaseCommand):
    help = 'Fija la cuota de cierre de los partidos que ya empezaron.'

    def handle(self, *args, **opts):
        fijar_cierres_pendientes()
        self.stdout.write(self.style.SUCCESS('Cuotas de cierre al día.'))
