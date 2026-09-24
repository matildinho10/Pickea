"""
Respaldo de la base de datos y de las fotos en un archivo .tar.gz.

Uso:  python manage.py respaldar                 (en ~/respaldos, guarda los últimos 14)
      python manage.py respaldar --guardar 30    (guarda los últimos 30)

La copia usa la función de respaldo de SQLite, así que es segura aunque haya
gente usando la página en ese momento.

Para RESTAURAR un respaldo (con la página detenida o recién recargada):
    1. Descomprimir:  tar -xzf ~/respaldos/pronostika_AAAA-MM-DD_HHMMSS.tar.gz -C /tmp/restaurar
    2. Copiar /tmp/restaurar/db.sqlite3 sobre ~/pickea/db.sqlite3 (y la carpeta media/ si hace falta)
    3. Presionar Reload en la pestaña Web.
"""
import sqlite3
import tarfile
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = 'Respalda la base de datos y las fotos en un archivo comprimido.'

    def add_arguments(self, parser):
        parser.add_argument('--carpeta', default=str(Path.home() / 'respaldos'),
                            help='Dónde guardar los respaldos (por defecto ~/respaldos).')
        parser.add_argument('--guardar', type=int, default=14,
                            help='Cuántos respaldos mantener; los más antiguos se borran.')

    def handle(self, *args, **opts):
        carpeta = Path(opts['carpeta'])
        carpeta.mkdir(parents=True, exist_ok=True)
        marca = timezone.localtime().strftime('%Y-%m-%d_%H%M%S')
        destino = carpeta / f'pronostika_{marca}.tar.gz'

        with tempfile.TemporaryDirectory() as temporal:
            copia = Path(temporal) / 'db.sqlite3'
            connection.ensure_connection()
            conexion_copia = sqlite3.connect(copia)
            connection.connection.backup(conexion_copia)   # copia consistente, aunque haya uso
            conexion_copia.close()

            with tarfile.open(destino, 'w:gz') as tar:
                tar.add(copia, arcname='db.sqlite3')
                fotos = Path(settings.MEDIA_ROOT)
                if fotos.exists():
                    tar.add(fotos, arcname='media')

        # Mantener solo los últimos N (los nombres llevan fecha, así que ordenan solos)
        respaldos = sorted(carpeta.glob('pronostika_*.tar.gz'))
        for viejo in respaldos[:-opts['guardar']] if opts['guardar'] > 0 else []:
            viejo.unlink()

        kb = destino.stat().st_size / 1024
        guardados = len(list(carpeta.glob('pronostika_*.tar.gz')))
        self.stdout.write(self.style.SUCCESS(
            f'Respaldo creado: {destino} ({kb:.0f} KB). Respaldos guardados: {guardados}.'))
