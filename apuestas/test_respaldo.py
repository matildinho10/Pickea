"""Pruebas del comando de respaldo."""
import sqlite3
import tarfile
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TransactionTestCase

from .models import Usuario


class RespaldoTests(TransactionTestCase):
    # Sin transacción envolvente, como en la vida real (si no, la copia de SQLite queda esperando)
    def test_respaldo_contiene_la_base_de_datos(self):
        Usuario.objects.create_user('ana', password='x')
        with tempfile.TemporaryDirectory() as carpeta:
            call_command('respaldar', carpeta=carpeta, stdout=StringIO())
            archivos = list(Path(carpeta).glob('pronostika_*.tar.gz'))
            self.assertEqual(len(archivos), 1)
            with tarfile.open(archivos[0]) as tar:
                tar.extract('db.sqlite3', carpeta, filter='data')
            conexion = sqlite3.connect(Path(carpeta) / 'db.sqlite3')
            nombres = [fila[0] for fila in conexion.execute('SELECT username FROM apuestas_usuario')]
            conexion.close()
            self.assertEqual(nombres, ['ana'])

    def test_borra_los_respaldos_antiguos(self):
        with tempfile.TemporaryDirectory() as carpeta:
            for marca in ['2026-09-01', '2026-09-02', '2026-09-03']:
                (Path(carpeta) / f'pronostika_{marca}_000000.tar.gz').write_bytes(b'viejo')
            call_command('respaldar', carpeta=carpeta, guardar=2, stdout=StringIO())
            restantes = sorted(p.name for p in Path(carpeta).glob('pronostika_*.tar.gz'))
            self.assertEqual(len(restantes), 2)
            self.assertNotIn('pronostika_2026-09-01_000000.tar.gz', restantes)
            self.assertNotIn('pronostika_2026-09-02_000000.tar.gz', restantes)
