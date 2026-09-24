"""Pruebas de la pestaña "Mis apuestas"."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from .models import MERCADOS, Apuesta, Equipo, Mercado, Opcion, Partido, Temporada, Usuario


class MisApuestasTests(TestCase):
    def setUp(self):
        self.t = Temporada.objects.create(nombre='PD 2026', anio=2026, activa=True)
        self.eq = [Equipo.objects.create(nombre=f'Equipo {i}', nombre_corto=f'E{i}') for i in range(6)]
        self.ana = Usuario.objects.create_user('ana', password='x')
        self.beto = Usuario.objects.create_user('beto', password='x')

    def partido(self, n):
        p = Partido.objects.create(temporada=self.t, fecha_numero=n, local=self.eq[2 * n],
                                   visita=self.eq[2 * n + 1], inicio=timezone.now() + timedelta(hours=n + 1))
        m = Mercado.objects.create(partido=p, tipo='1x2')
        for i, ((codigo, etiqueta), c) in enumerate(zip(MERCADOS['1x2'][2], ['2.00', '3.50', '4.00'])):
            Opcion.objects.create(mercado=m, codigo=codigo, orden=i, cuota=Decimal(c),
                                  etiqueta=etiqueta.format(local=p.local, visita=p.visita))
        return p

    def apostar(self, usuario, p, codigo, unidades):
        return Apuesta.confirmar(usuario, Opcion.objects.get(mercado__partido=p, codigo=codigo), unidades)

    def test_requiere_sesion(self):
        r = self.client.get('/mis-apuestas/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/entrar/', r.url)

    def test_activas_e_historial(self):
        jugado, pendiente = self.partido(0), self.partido(1)
        self.apostar(self.ana, jugado, '1', 4)        # gana: +4.00
        self.apostar(self.ana, jugado, 'X', 2)        # pierde: -2.00
        self.apostar(self.ana, pendiente, '2', 3)     # activa: si gana +9.00
        self.apostar(self.beto, pendiente, '1', 5)    # de otro usuario: no debe aparecer
        jugado.goles_local, jugado.goles_visita = 1, 0
        jugado.save()
        jugado.liquidar()
        self.client.force_login(self.ana)

        r = self.client.get('/mis-apuestas/')
        self.assertContains(r, 'Activas (1)')
        self.assertContains(r, 'E2 vs E3')
        self.assertContains(r, '+9.00 u')
        self.assertNotContains(r, 'E0 vs E1')
        self.assertEqual(len(r.context['grupos']), 1)
        self.assertEqual(r.context['unidades_en_juego'], 3)

        r = self.client.get('/mis-apuestas/?vista=historial')
        self.assertContains(r, 'E0 vs E1')
        self.assertNotContains(r, 'E2 vs E3')
        grupo = r.context['grupos'][0]
        self.assertEqual(len(grupo.apuestas), 2)
        self.assertEqual(grupo.ganancia, Decimal('2.00'))   # +4 - 2
        self.assertContains(r, 'Ganada')
        self.assertContains(r, 'Perdida')

    def test_historial_vacio(self):
        self.client.force_login(self.ana)
        r = self.client.get('/mis-apuestas/?vista=historial')
        self.assertContains(r, 'Todavía no tienes apuestas decididas')
