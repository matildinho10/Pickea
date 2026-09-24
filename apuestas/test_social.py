"""Pruebas de seguir tipsters, foto de perfil y la guía."""
import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from .models import Seguimiento, Temporada, Usuario

MEDIA_PRUEBA = tempfile.mkdtemp()


def imagen_subida(ancho=600, alto=400, formato='PNG'):
    buffer = BytesIO()
    Image.new('RGB', (ancho, alto), (163, 35, 27)).save(buffer, format=formato)
    return SimpleUploadedFile(f'mi foto.{formato.lower()}', buffer.getvalue(), content_type=f'image/{formato.lower()}')


class SeguirTests(TestCase):
    def setUp(self):
        Temporada.objects.create(nombre='PD 2026', anio=2026, activa=True)
        self.ana = Usuario.objects.create_user('ana', password='x')
        self.beto = Usuario.objects.create_user('beto', password='x')

    def test_seguir_y_dejar_de_seguir(self):
        self.client.force_login(self.ana)
        self.client.post('/u/beto/seguir/')
        self.assertTrue(self.ana.sigue_a(self.beto))
        r = self.client.get('/u/beto/')
        self.assertContains(r, 'Siguiendo ✓')
        self.assertContains(r, '<strong>1</strong> seguidor<')
        self.client.post('/u/beto/seguir/')
        self.assertFalse(self.ana.sigue_a(self.beto))

    def test_no_puede_seguirse_a_si_mismo(self):
        self.client.force_login(self.ana)
        self.client.post('/u/ana/seguir/')
        self.assertEqual(Seguimiento.objects.count(), 0)
        self.assertContains(self.client.get('/u/ana/'), 'Editar perfil')

    def test_sin_sesion_pide_entrar(self):
        r = self.client.post('/u/beto/seguir/')
        self.assertIn('/entrar/', r.url)
        self.assertContains(self.client.get('/u/beto/'), 'href="/entrar/?next=/u/beto/"')

    def test_pestana_siguiendo_del_ranking(self):
        self.client.force_login(self.ana)
        r = self.client.get('/?ver=siguiendo')
        self.assertContains(r, 'Todavía no sigues a nadie')
        Seguimiento.objects.create(seguidor=self.ana, seguido=self.beto)
        r = self.client.get('/?ver=siguiendo')
        self.assertEqual(r.context['n_siguiendo'], 1)
        self.assertNotContains(r, 'Todavía no sigues a nadie')


@override_settings(MEDIA_ROOT=MEDIA_PRUEBA)
class FotoTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_PRUEBA, ignore_errors=True)

    def setUp(self):
        self.ana = Usuario.objects.create_user('ana', password='x')
        self.client.force_login(self.ana)

    def test_subir_foto_la_deja_cuadrada_y_liviana(self):
        r = self.client.post('/cuenta/', {'foto': imagen_subida(1200, 800)})
        self.assertRedirects(r, '/u/ana/', fetch_redirect_response=False)
        self.ana.refresh_from_db()
        self.assertTrue(self.ana.foto.name.startswith('fotos/'))
        self.assertTrue(self.ana.foto.name.endswith('.jpg'))
        with Image.open(self.ana.foto.path) as img:
            self.assertEqual(img.size, (256, 256))
            self.assertEqual(img.format, 'JPEG')
        self.assertContains(self.client.get('/u/ana/'), self.ana.foto.url)

    def test_cambiar_foto_borra_la_anterior(self):
        self.client.post('/cuenta/', {'foto': imagen_subida()})
        self.ana.refresh_from_db()
        anterior = self.ana.foto.path
        self.client.post('/cuenta/', {'foto': imagen_subida(formato='JPEG')})
        self.ana.refresh_from_db()
        self.assertNotEqual(self.ana.foto.path, anterior)
        self.assertFalse(self.ana.foto.storage.exists(anterior))

    def test_quitar_foto(self):
        self.client.post('/cuenta/', {'foto': imagen_subida()})
        self.ana.refresh_from_db()
        ruta = self.ana.foto.path
        self.client.post('/cuenta/', {'quitar': '1'})
        self.ana.refresh_from_db()
        self.assertFalse(self.ana.foto)
        self.assertFalse(self.ana.foto.storage.exists(ruta))

    def test_rechaza_archivos_que_no_son_imagen(self):
        falso = SimpleUploadedFile('virus.png', b'esto no es una imagen', content_type='image/png')
        r = self.client.post('/cuenta/', {'foto': falso})
        self.assertEqual(r.status_code, 200)
        self.ana.refresh_from_db()
        self.assertFalse(self.ana.foto)

    def test_cuenta_requiere_sesion(self):
        self.client.logout()
        self.assertIn('/entrar/', self.client.get('/cuenta/').url)


class GuiaTests(TestCase):
    def test_guia_explica_los_conceptos(self):
        r = self.client.get('/como-funciona/')
        self.assertEqual(r.status_code, 200)
        for ancla in ['id="p-value"', 'id="clv"', 'id="roi"', 'id="partidos-efectivos"', 'id="unidades"']:
            self.assertContains(r, ancla)

    def test_ranking_dice_p_value(self):
        Temporada.objects.create(nombre='PD 2026', anio=2026, activa=True)
        r = self.client.get('/')
        self.assertContains(r, 'p-value')
        self.assertNotContains(r, 'p-valor')
        self.assertContains(r, '/como-funciona/#p-value')


class PestanasSinSesionTests(TestCase):
    def setUp(self):
        Temporada.objects.create(nombre='PD 2026', anio=2026, activa=True)
        self.ana = Usuario.objects.create_user('ana', password='clave-segura-123')

    def test_la_barra_muestra_todas_las_pestanas(self):
        r = self.client.get('/')
        self.assertContains(r, '>Mis apuestas</a>')
        self.assertContains(r, '>Mi perfil</a>')

    def test_sin_sesion_explica_por_que_hay_que_entrar(self):
        r = self.client.get('/mis-apuestas/', follow=True)
        self.assertContains(r, 'Inicia sesión para ver tus apuestas.')
        r = self.client.get('/mi-perfil/', follow=True)
        self.assertContains(r, 'Inicia sesión para ver tu perfil.')
        self.assertContains(r, 'href="/registro/?next=/mi-perfil/"')

    def test_despues_de_entrar_vuelve_a_donde_queria_ir(self):
        r = self.client.post('/entrar/', {'username': 'ana', 'password': 'clave-segura-123',
                                          'next': '/mis-apuestas/'})
        self.assertEqual(r.url, '/mis-apuestas/')
        self.assertEqual(self.client.get('/mi-perfil/').url, '/u/ana/')

    def test_no_redirige_a_otros_sitios(self):
        r = self.client.post('/entrar/', {'username': 'ana', 'password': 'clave-segura-123',
                                          'next': 'https://sitio-malo.com/'})
        self.assertEqual(r.url, '/partidos/')
