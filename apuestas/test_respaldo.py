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


class RespaldoAutomaticoTests(TransactionTestCase):
    def setUp(self):
        from . import respaldo_automatico
        self.modulo = respaldo_automatico
        self.modulo._ultima_revision = 0.0
        self.carpeta = tempfile.TemporaryDirectory()
        self.ajustes = self.settings(RESPALDOS_DIR=self.carpeta.name)
        self.ajustes.enable()

    def tearDown(self):
        self.ajustes.disable()
        self.carpeta.cleanup()

    def respaldos(self):
        return list(Path(self.carpeta.name).glob('pronostika_*.tar.gz'))

    def test_crea_uno_si_no_hay_ninguno_y_no_repite_el_mismo_dia(self):
        import time
        self.assertTrue(self.modulo.revisar_respaldo())
        self.assertEqual(len(self.respaldos()), 1)
        # Dos horas después: ya hay uno de hoy, no crea otro
        self.assertFalse(self.modulo.revisar_respaldo(ahora=time.time() + 2 * 3600))
        self.assertEqual(len(self.respaldos()), 1)

    def test_revisa_como_maximo_una_vez_por_hora(self):
        import time
        ahora = time.time()
        self.modulo._ultima_revision = ahora - 60
        self.assertFalse(self.modulo.revisar_respaldo(ahora=ahora))
        self.assertEqual(self.respaldos(), [])

    def test_crea_otro_si_el_ultimo_tiene_mas_de_un_dia(self):
        import os
        import time
        viejo = Path(self.carpeta.name) / 'pronostika_2026-09-01_000000.tar.gz'
        viejo.write_bytes(b'viejo')
        hace_dos_dias = time.time() - 2 * 24 * 3600
        os.utime(viejo, (hace_dos_dias, hace_dos_dias))
        self.assertTrue(self.modulo.revisar_respaldo())
        self.assertEqual(len(self.respaldos()), 2)

    def test_la_pagina_lo_activa_solo_si_esta_habilitado(self):
        with self.settings(RESPALDO_AUTOMATICO=False):
            self.client.get('/como-funciona/')
        self.assertEqual(self.respaldos(), [])
        with self.settings(RESPALDO_AUTOMATICO=True):
            self.client.get('/como-funciona/')
        self.assertEqual(len(self.respaldos()), 1)
