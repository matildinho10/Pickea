"""Pruebas del orden del ranking, borrar cuenta y páginas legales."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from .models import MERCADOS, Apuesta, Equipo, Mercado, Opcion, Partido, Seguimiento, Temporada, Usuario


class OrdenRankingTests(TestCase):
    """
    30 partidos: 6 empates (cada 5) y 24 triunfos locales. Cuotas: 1 = 1.50, X = 7.00, 2 = 9.00.
      - constante: 10 u al 1 siempre -> 24 x (+5) + 6 x (-10) = +60 u, ROI 20%, z = 60/raiz(1200) = 1.73
      - grande:    10 u al X siempre -> 6 x (+60) + 24 x (-10) = +120 u, ROI 40%, z = 120/raiz(24000) = 0.77
      - fino:       1 u al X siempre -> +12 u, ROI 40%, z = 0.77
    Por p-value gana "constante"; por ganancia, "grande".
    """

    def setUp(self):
        self.t = Temporada.objects.create(nombre='PD 2026', anio=2026, activa=True)
        a = Equipo.objects.create(nombre='A', nombre_corto='A')
        b = Equipo.objects.create(nombre='B', nombre_corto='B')
        usuarios = {n: Usuario.objects.create_user(n, password='x') for n in ('constante', 'grande', 'fino')}
        for n in range(30):
            p = Partido.objects.create(temporada=self.t, fecha_numero=1, local=a, visita=b,
                                       inicio=timezone.now() + timedelta(hours=n + 1))
            m = Mercado.objects.create(partido=p, tipo='1x2')
            ops = {}
            for i, ((codigo, etiqueta), c) in enumerate(zip(MERCADOS['1x2'][2], ['1.50', '7.00', '9.00'])):
                ops[codigo] = Opcion.objects.create(mercado=m, codigo=codigo, orden=i, cuota=Decimal(c),
                                                    etiqueta=etiqueta)
            Apuesta.confirmar(usuarios['constante'], ops['1'], 10)
            Apuesta.confirmar(usuarios['grande'], ops['X'], 10)
            Apuesta.confirmar(usuarios['fino'], ops['X'], 1)
            p.goles_local, p.goles_visita = (1, 1) if n % 5 == 0 else (2, 0)
            p.save()
            p.liquidar()

    def orden_de(self, url):
        return [e.usuario.username for e in self.client.get(url).context['en_ranking']]

    def test_por_defecto_ordena_por_p_value(self):
        self.assertEqual(self.orden_de('/')[0], 'constante')

    def test_ordenar_por_ganancia(self):
        orden = self.orden_de('/?orden=ganancia')
        self.assertEqual(orden[0], 'grande')
        r = self.client.get('/?orden=ganancia')
        self.assertContains(r, 'Ordenado por ganancia')
        self.assertContains(r, 'no consideran cuánta suerte')

    def test_ordenar_por_roi(self):
        r = self.client.get('/?orden=roi')
        rois = [e.roi for e in r.context['en_ranking']]
        self.assertEqual(rois, sorted(rois, reverse=True))

    def test_orden_desconocido_usa_p_value(self):
        self.assertEqual(self.client.get('/?orden=xyz').context['orden'], 'pvalue')

    def test_los_enlaces_conservan_el_periodo(self):
        r = self.client.get('/?periodo=historico&orden=roi')
        self.assertContains(r, 'href="?periodo=temporada&amp;orden=roi"')


class BorrarCuentaTests(TestCase):
    def setUp(self):
        self.ana = Usuario.objects.create_user('ana', password='clave-segura-123')
        self.beto = Usuario.objects.create_user('beto', password='x')
        Seguimiento.objects.create(seguidor=self.ana, seguido=self.beto)
        Seguimiento.objects.create(seguidor=self.beto, seguido=self.ana)
        self.client.force_login(self.ana)

    def test_contrasena_incorrecta_no_borra(self):
        r = self.client.post('/cuenta/borrar/', {'password': 'mala'})
        self.assertContains(r, 'La contraseña no es correcta')
        self.assertTrue(Usuario.objects.filter(username='ana').exists())

    def test_borra_la_cuenta_y_todo_lo_asociado(self):
        r = self.client.post('/cuenta/borrar/', {'password': 'clave-segura-123'})
        self.assertContains(r, 'Cuenta borrada')
        self.assertFalse(Usuario.objects.filter(username='ana').exists())
        self.assertEqual(Seguimiento.objects.count(), 0)
        self.assertIn('/entrar/', self.client.get('/mis-apuestas/').url)   # quedó sin sesión

    def test_editar_perfil_ofrece_borrar(self):
        self.assertContains(self.client.get('/cuenta/'), 'Borrar mi cuenta')


class PaginasLegalesTests(TestCase):
    def test_terminos_y_privacidad(self):
        self.assertContains(self.client.get('/terminos/'), 'No se juega con dinero real')
        self.assertContains(self.client.get('/privacidad/'), 'Tu correo nunca se muestra')

    def test_el_pie_las_enlaza_en_todas_las_paginas(self):
        Temporada.objects.create(nombre='PD 2026', anio=2026, activa=True)
        r = self.client.get('/')
        self.assertContains(r, 'href="/terminos/"')
        self.assertContains(r, 'href="/privacidad/"')

    def test_el_registro_las_enlaza(self):
        r = self.client.get('/registro/')
        self.assertContains(r, 'Tengo 18 años o más')
        self.assertContains(r, 'href="/terminos/"')
