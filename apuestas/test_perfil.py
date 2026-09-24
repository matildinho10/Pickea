"""Pruebas del perfil público y del gráfico."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from . import grafico
from .models import MERCADOS, Apuesta, Equipo, Mercado, Opcion, Partido, Temporada, Usuario


class PerfilTests(TestCase):
    def setUp(self):
        self.t = Temporada.objects.create(nombre='PD 2026', anio=2026, activa=True)
        self.eq = [Equipo.objects.create(nombre=f'Equipo {i}', nombre_corto=f'E{i}') for i in range(6)]
        self.ana = Usuario.objects.create_user('la_cuota', password='x')

    def partido(self, n):
        p = Partido.objects.create(temporada=self.t, fecha_numero=n, local=self.eq[2 * n],
                                   visita=self.eq[2 * n + 1], inicio=timezone.now() + timedelta(hours=n + 1))
        m = Mercado.objects.create(partido=p, tipo='1x2')
        for i, ((codigo, etiqueta), c) in enumerate(zip(MERCADOS['1x2'][2], ['2.00', '3.50', '4.00'])):
            Opcion.objects.create(mercado=m, codigo=codigo, orden=i, cuota=Decimal(c),
                                  etiqueta=etiqueta.format(local=p.local, visita=p.visita))
        return p

    def jugar(self, p, gl, gv):
        p.fijar_cuotas_cierre()
        p.goles_local, p.goles_visita = gl, gv
        p.save()
        p.liquidar()

    def test_perfil_con_apuestas(self):
        a, b, pendiente = self.partido(0), self.partido(1), self.partido(2)
        Apuesta.confirmar(self.ana, Opcion.objects.get(mercado__partido=a, codigo='1'), 4)   # +4
        Apuesta.confirmar(self.ana, Opcion.objects.get(mercado__partido=b, codigo='2'), 3)   # -3
        Apuesta.confirmar(self.ana, Opcion.objects.get(mercado__partido=pendiente, codigo='X'), 5)
        self.jugar(a, 2, 0)
        self.jugar(b, 1, 0)

        r = self.client.get('/u/la_cuota/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '@la_cuota')
        self.assertContains(r, '>LC<')                        # iniciales del avatar
        self.assertContains(r, 'Evidencia de habilidad')
        self.assertContains(r, '+14.3%')                      # ROI = (4 - 3) / (4 + 3)
        self.assertContains(r, 'Aún no entra al ranking')
        self.assertContains(r, 'E0 vs E1')
        self.assertContains(r, 'E4 vs E5')                    # la apuesta abierta es pública
        self.assertEqual(len(r.context['abiertas']), 1)
        self.assertContains(r, 'id="abiertas"')
        # En el ranking aparece cuántas apuestas abiertas tiene
        self.assertContains(self.client.get('/?bajo=1'), '1 abierta<')
        g = r.context['grafico']
        self.assertEqual([d['a'] for d in g['datos']], [0, 4, 1])
        self.assertEqual(g['n_partidos'], 2)

    def test_perfil_sin_apuestas_e_historico(self):
        for url in ['/u/la_cuota/', '/u/la_cuota/?periodo=historico']:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, 'Aún no hay partidos decididos para graficar')
            self.assertIsNone(r.context['grafico'])

    def test_mi_perfil_marca_la_pestana(self):
        self.client.force_login(self.ana)
        r = self.client.get('/u/la_cuota/')
        self.assertEqual(r.context['seccion'], 'perfil')
        self.assertContains(r, 'Ver todas')


class GraficoTests(TestCase):
    def test_paso_redondo(self):
        self.assertEqual(grafico.paso_redondo(88.5), 50)
        self.assertEqual(grafico.paso_redondo(12), 5)
        self.assertEqual(grafico.paso_redondo(400), 100)
        self.assertEqual(grafico.paso_redondo(0), 1)

    def test_eje_incluye_el_cero_y_los_extremos(self):
        class P:
            inicio = timezone.now()
            def __str__(self):
                return 'A vs B'
        g = grafico.preparar([(P(), -12.0), (P(), 30.0)])
        valores = [m['valor'] for m in g['marcas']]
        self.assertIn(0, valores)
        self.assertLessEqual(min(valores), -12)
        self.assertGreaterEqual(max(valores), 30)
        self.assertIsNone(grafico.preparar([]))
