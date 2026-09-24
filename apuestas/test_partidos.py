"""Pruebas de la página de partidos, la boleta y el registro."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from .models import MERCADOS, Apuesta, Equipo, Mercado, Opcion, Partido, Temporada, Usuario


class PartidosTests(TestCase):
    def setUp(self):
        t = Temporada.objects.create(nombre='Primera División 2026', anio=2026, activa=True)
        cc = Equipo.objects.create(nombre='Colo-Colo', nombre_corto='Colo-Colo')
        ev = Equipo.objects.create(nombre='Everton', nombre_corto='Everton')
        self.partido = Partido.objects.create(temporada=t, fecha_numero=24, local=cc, visita=ev,
                                              inicio=timezone.now() + timedelta(days=1))
        for tipo, cuotas in (('1x2', ['1.72', '3.60', '4.80']), ('ou25', ['1.95', '1.85']),
                             ('btts', ['1.80', '1.95'])):
            m = Mercado.objects.create(partido=self.partido, tipo=tipo)
            for i, ((codigo, etiqueta), c) in enumerate(zip(MERCADOS[tipo][2], cuotas)):
                Opcion.objects.create(mercado=m, codigo=codigo, orden=i, cuota=Decimal(c),
                                      etiqueta=etiqueta.format(local=cc, visita=ev))
        self.local = Opcion.objects.get(mercado__tipo='1x2', codigo='1')
        self.ana = Usuario.objects.create_user('ana', password='clave-segura-123')

    def test_pagina_muestra_cuotas_con_punto(self):
        r = self.client.get('/partidos/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Fecha 24')
        self.assertContains(r, 'data-cuota="1.72"')
        self.assertContains(r, 'Ambos marcan')          # mercado adicional
        self.assertContains(r, 'Inicia sesión para apostar')

    def test_sin_sesion_no_puede_apostar(self):
        r = self.client.post('/apostar/', {'opcion': self.local.pk, 'unidades': 3})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/entrar/', r.url)
        self.assertEqual(Apuesta.objects.count(), 0)

    def test_apuesta_usa_la_cuota_del_servidor(self):
        self.client.force_login(self.ana)
        # El navegador intenta mandar una cuota inventada: se ignora
        r = self.client.post('/apostar/', {'opcion': self.local.pk, 'unidades': 3,
                                           'cuota': '50.00', 'cuota_vista': '1.72'}, follow=True)
        a = Apuesta.objects.get()
        self.assertEqual(a.cuota, Decimal('1.72'))
        self.assertEqual(a.unidades, 3)
        self.assertContains(r, 'Apuesta registrada')
        self.assertContains(r, 'Tus apuestas en esta fecha')

    def test_avisa_si_la_cuota_cambio(self):
        self.client.force_login(self.ana)
        Opcion.objects.filter(pk=self.local.pk).update(cuota=Decimal('1.65'))
        r = self.client.post('/apostar/', {'opcion': self.local.pk, 'unidades': 2, 'cuota_vista': '1.72'},
                             follow=True)
        self.assertEqual(Apuesta.objects.get().cuota, Decimal('1.65'))
        self.assertContains(r, 'la cuota cambió de 1.72 a 1.65')

    def test_unidades_invalidas(self):
        self.client.force_login(self.ana)
        for u in ('0', '11', 'abc', ''):
            r = self.client.post('/apostar/', {'opcion': self.local.pk, 'unidades': u}, follow=True)
            self.assertContains(r, 'Las unidades deben estar entre 1 y 10.')
        self.assertEqual(Apuesta.objects.count(), 0)

    def test_partido_empezado_esta_cerrado(self):
        self.client.force_login(self.ana)
        Partido.objects.filter(pk=self.partido.pk).update(inicio=timezone.now() - timedelta(minutes=1))
        r = self.client.post('/apostar/', {'opcion': self.local.pk, 'unidades': 3}, follow=True)
        self.assertContains(r, 'ya están cerradas')
        self.assertEqual(Apuesta.objects.count(), 0)
        # Al abrir la página se fija la cuota de cierre y los botones quedan deshabilitados
        r = self.client.get('/partidos/?fecha=24')
        self.assertContains(r, 'Cerrado')
        self.local.refresh_from_db()
        self.assertEqual(self.local.cuota_cierre, Decimal('1.72'))

    def test_inicio_de_sesion(self):
        # El registro con correo se prueba en test_correos.py
        r = self.client.post('/entrar/', {'username': 'ana', 'password': 'clave-segura-123'}, follow=True)
        self.assertContains(r, '@ana')
