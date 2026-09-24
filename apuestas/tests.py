"""Pruebas automáticas de las reglas. Se corren con:  python manage.py test"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import MERCADOS, Apuesta, Equipo, Mercado, Opcion, Partido, Temporada, Usuario


class ReglasApuestaTests(TestCase):
    def setUp(self):
        t = Temporada.objects.create(nombre='PD 2026', anio=2026, activa=True)
        cc = Equipo.objects.create(nombre='Colo-Colo', nombre_corto='Colo-Colo')
        ev = Equipo.objects.create(nombre='Everton', nombre_corto='Everton')
        self.partido = Partido.objects.create(temporada=t, fecha_numero=24, local=cc, visita=ev,
                                              inicio=timezone.now() + timedelta(hours=2))
        self.m1x2 = self.crear_mercado('1x2', {'1': '1.72', 'X': '3.60', '2': '4.80'})
        self.mdnb = self.crear_mercado('dnb', {'1': '1.30', '2': '3.40'})
        self.usuario = Usuario.objects.create_user('ana', password='x')

    def crear_mercado(self, tipo, cuotas):
        m = Mercado.objects.create(partido=self.partido, tipo=tipo)
        for i, (codigo, etiqueta) in enumerate(MERCADOS[tipo][2]):
            Opcion.objects.create(mercado=m, codigo=codigo, etiqueta=etiqueta, orden=i,
                                  cuota=Decimal(cuotas[codigo]))
        return m

    def opcion(self, mercado, codigo):
        return mercado.opciones.get(codigo=codigo)

    def test_cuota_queda_fija_aunque_el_mercado_cambie(self):
        local = self.opcion(self.m1x2, '1')
        a = Apuesta.confirmar(self.usuario, local, 4)
        Opcion.objects.filter(pk=local.pk).update(cuota=Decimal('1.50'))
        a.refresh_from_db()
        self.assertEqual(a.cuota, Decimal('1.72'))
        self.assertEqual(a.cuotas_mercado, {'1': '1.72', 'X': '3.60', '2': '4.80'})

    def test_usa_la_cuota_vigente_de_la_base(self):
        local = self.opcion(self.m1x2, '1')
        Opcion.objects.filter(pk=local.pk).update(cuota=Decimal('1.65'))
        a = Apuesta.confirmar(self.usuario, local, 1)   # objeto en memoria aún dice 1.72
        self.assertEqual(a.cuota, Decimal('1.65'))

    def test_suma_inversas_del_mercado(self):
        a = Apuesta.confirmar(self.usuario, self.opcion(self.m1x2, 'X'), 2)
        esperado = 1 / Decimal('1.72') + 1 / Decimal('3.60') + 1 / Decimal('4.80')
        self.assertAlmostEqual(float(a.suma_inversas), float(esperado), places=4)

    def test_unidades_fuera_de_rango(self):
        for u in (0, 11):
            with self.assertRaises(ValidationError):
                Apuesta.confirmar(self.usuario, self.opcion(self.m1x2, '1'), u)

    def test_cierra_al_inicio_del_partido(self):
        with self.assertRaises(ValidationError):
            Apuesta.confirmar(self.usuario, self.opcion(self.m1x2, '1'), 3, ahora=self.partido.inicio)

    def test_liquidacion_y_ganancia(self):
        pierde = Apuesta.confirmar(self.usuario, self.opcion(self.m1x2, '1'), 4)
        gana = Apuesta.confirmar(self.usuario, self.opcion(self.m1x2, 'X'), 3)
        nula = Apuesta.confirmar(self.usuario, self.opcion(self.mdnb, '2'), 5)
        self.partido.goles_local = self.partido.goles_visita = 1
        self.partido.save()
        self.partido.liquidar()
        # 1-1: gana el empate, pierde el local, "empate no válido" es nula
        for a in (gana, pierde, nula):
            a.refresh_from_db()
        self.assertEqual(gana.ganancia, Decimal('3') * (Decimal('3.60') - 1))
        self.assertEqual(pierde.ganancia, Decimal('-4'))
        self.assertEqual(nula.ganancia, 0)

    def test_cuota_de_cierre_y_clv(self):
        local = self.opcion(self.m1x2, '1')
        a = Apuesta.confirmar(self.usuario, local, 2)
        Opcion.objects.filter(pk=local.pk).update(cuota=Decimal('1.60'))
        self.partido.fijar_cuotas_cierre()
        a.refresh_from_db()
        self.assertEqual(a.opcion.cuota_cierre, Decimal('1.60'))
        self.assertAlmostEqual(float(a.clv), 1.72 / 1.60 - 1, places=6)


class EstadisticasTests(TestCase):
    """
    Ejemplo calculado a mano (cuotas 1X2: 2.00 / 3.50 / 4.00):
      Partido A (gana local): 4 u al 1 @ 2.00 -> +4 ;  2 u al X @ 3.50 -> -2   => G_A = +2, S_A = 6
      Partido B (gana local): 3 u al 2 @ 4.00 -> -3                            => G_B = -3, S_B = 3
      Partido C (empate):     5 u "empate no válido" -> nula, NO cuenta
    """

    def setUp(self):
        self.t = Temporada.objects.create(nombre='PD 2026', anio=2026, activa=True)
        self.eq = [Equipo.objects.create(nombre=f'Equipo {i}', nombre_corto=f'E{i}') for i in range(6)]
        self.ana = Usuario.objects.create_user('ana', password='x')

    def partido(self, n, horas):
        p = Partido.objects.create(temporada=self.t, fecha_numero=n, local=self.eq[2 * n], visita=self.eq[2 * n + 1],
                                   inicio=timezone.now() + timedelta(hours=horas))
        for tipo, cuotas in (('1x2', ['2.00', '3.50', '4.00']), ('dnb', ['1.50', '2.60'])):
            m = Mercado.objects.create(partido=p, tipo=tipo)
            for i, ((codigo, etiqueta), c) in enumerate(zip(MERCADOS[tipo][2], cuotas)):
                Opcion.objects.create(mercado=m, codigo=codigo, etiqueta=etiqueta, orden=i, cuota=Decimal(c))
        return p

    def apostar(self, p, tipo, codigo, unidades):
        return Apuesta.confirmar(self.ana, Opcion.objects.get(mercado__partido=p, mercado__tipo=tipo, codigo=codigo),
                                 unidades)

    def cerrar(self, p, cierres, gl, gv):
        for codigo, c in cierres.items():
            Opcion.objects.filter(mercado__partido=p, mercado__tipo='1x2', codigo=codigo).update(cuota=Decimal(c))
        p.fijar_cuotas_cierre()
        p.goles_local, p.goles_visita = gl, gv
        p.save()
        p.liquidar()

    def preparar_ejemplo(self):
        a, b, c = self.partido(0, 1), self.partido(1, 2), self.partido(2, 3)
        self.apostar(a, '1x2', '1', 4)
        self.apostar(a, '1x2', 'X', 2)
        self.apostar(b, '1x2', '2', 3)
        self.apostar(c, 'dnb', '1', 5)
        self.cerrar(a, {'1': '1.80'}, 2, 0)          # CLV del "1": 2.00/1.80 - 1 = +11.1%
        self.cerrar(b, {'2': '4.40'}, 1, 0)          # CLV del "2": 4.00/4.40 - 1 = -9.1%
        self.cerrar(c, {}, 1, 1)

    def test_formulas_del_ejemplo(self):
        from .estadisticas import estadisticas_usuario
        self.preparar_ejemplo()
        e = estadisticas_usuario(self.ana)

        self.assertEqual(e.apuestas, 3)                              # la nula no cuenta
        self.assertEqual(e.unidades, 9)
        self.assertAlmostEqual(e.ganancia, -1)
        self.assertAlmostEqual(e.roi, -1 / 9)
        self.assertEqual(e.partidos, 2)
        self.assertAlmostEqual(e.z, -1 / 13 ** 0.5)                  # (2 - 3) / raiz(4 + 9)
        self.assertAlmostEqual(e.p_valor, 0.609244, places=5)        # 1 - Phi(-0.27735)
        self.assertAlmostEqual(e.partidos_efectivos, 81 / 45)        # (6 + 3)^2 / (36 + 9)
        self.assertAlmostEqual(e.cuota_promedio, (2 + 3.5 + 4) / 3)
        self.assertAlmostEqual(e.clv, (4 * (2 / 1.8 - 1) + 2 * 0 + 3 * (4 / 4.4 - 1)) / 9)

        self.assertEqual([round(v, 6) for _, v in e.serie], [2, -1])  # unidades acumuladas por partido
        self.assertFalse(e.en_ranking)

    def test_usuario_sin_apuestas(self):
        from .estadisticas import estadisticas_usuario
        e = estadisticas_usuario(self.ana)
        self.assertEqual(e.apuestas, 0)
        self.assertIsNone(e.z)
        self.assertIsNone(e.roi)

    def test_ranking_separa_bajo_el_minimo(self):
        from .estadisticas import ranking
        self.preparar_ejemplo()
        en_ranking, bajo_minimo = ranking(self.t)
        self.assertEqual(en_ranking, [])
        self.assertEqual([e.usuario for e in bajo_minimo], [self.ana])


class PaginasTests(TestCase):
    def setUp(self):
        Temporada.objects.create(nombre='PD 2026', anio=2026, activa=True)
        Usuario.objects.create_user('ana', password='x')

    def test_ranking_carga(self):
        for url in ['/', '/?periodo=historico', '/?bajo=1']:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, 'Ranking')

    def test_perfil_inexistente_da_404(self):
        self.assertEqual(self.client.get('/u/ana/').status_code, 200)
        self.assertEqual(self.client.get('/u/nadie/').status_code, 404)


class FormatoTests(TestCase):
    def test_filtros(self):
        from .templatetags.formato import ancho_barra, con_signo, porcentaje, pvalor
        self.assertEqual(con_signo(12.345), '+12.3')
        self.assertEqual(con_signo(-4, 2), '−4.00')
        self.assertEqual(con_signo(0.01), '0.0')
        self.assertEqual(porcentaje(0.078), '+7.8%')
        self.assertEqual(pvalor(0.0004), '<0.001')
        self.assertEqual(pvalor(0.1234), '0.123')
        self.assertEqual(ancho_barra(-1), 0)
        self.assertEqual(ancho_barra(2), 50)
        self.assertEqual(ancho_barra(9), 100)
