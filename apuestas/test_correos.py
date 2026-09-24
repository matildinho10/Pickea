"""Pruebas del registro con correo, recuperar contraseña y cambiar correo/contraseña."""
import re

from django.core import mail
from django.test import TestCase

from .models import Temporada, Usuario

CLAVE = 'unaClaveLarga!9'


def enlace_del_correo(correo):
    return re.search(r'https?://testserver(/\S+)', correo.body).group(1)


class RegistroConCorreoTests(TestCase):
    def setUp(self):
        Temporada.objects.create(nombre='PD 2026', anio=2026, activa=True)

    def registrar(self, username='nuevo', email='nuevo@ejemplo.com'):
        return self.client.post('/registro/', {'username': username, 'email': email,
                                               'password1': CLAVE, 'password2': CLAVE, 'acepto': 'on'})

    def test_registro_envia_correo_y_la_cuenta_queda_inactiva(self):
        r = self.registrar()
        self.assertContains(r, 'Revisa tu correo')
        usuario = Usuario.objects.get(username='nuevo')
        self.assertFalse(usuario.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['nuevo@ejemplo.com'])
        self.assertIn('Activa tu cuenta', mail.outbox[0].subject)
        self.assertIn('/activar/', mail.outbox[0].body)
        self.assertIn('Activar mi cuenta', mail.outbox[0].alternatives[0].content)   # versión con diseño

    def test_no_puede_entrar_sin_activar_y_se_le_explica(self):
        self.registrar()
        r = self.client.post('/entrar/', {'username': 'nuevo', 'password': CLAVE})
        self.assertContains(r, 'todavía no está activada')
        self.assertContains(r, 'Reenviar el correo de activación')
        # Con la contraseña mala no revela nada
        r = self.client.post('/entrar/', {'username': 'nuevo', 'password': 'mala'})
        self.assertNotContains(r, 'todavía no está activada')

    def test_el_enlace_activa_la_cuenta_una_sola_vez(self):
        self.registrar()
        enlace = enlace_del_correo(mail.outbox[0])
        r = self.client.get(enlace, follow=True)
        self.assertContains(r, 'Cuenta activada')
        self.assertContains(r, '@nuevo')                   # quedó con la sesión iniciada
        usuario = Usuario.objects.get(username='nuevo')
        self.assertTrue(usuario.is_active)
        self.assertTrue(usuario.email_verificado)
        self.client.post('/salir/')
        self.assertEqual(self.client.get(enlace).status_code, 400)   # ya no sirve

    def test_enlace_falso(self):
        self.assertContains(self.client.get('/activar/MQ/codigo-falso/'), 'ya no sirve', status_code=400)

    def test_correo_obligatorio_y_unico(self):
        r = self.client.post('/registro/', {'username': 'a', 'password1': CLAVE, 'password2': CLAVE})
        self.assertFalse(Usuario.objects.filter(username='a').exists())
        self.registrar('primero', 'repetido@ejemplo.com')
        r = self.registrar('segundo', 'REPETIDO@ejemplo.com')
        self.assertContains(r, 'Ya hay una cuenta con ese correo')

    def test_reenviar_activacion(self):
        self.registrar()
        mail.outbox.clear()
        r = self.client.post('/reenviar-activacion/', {'email': 'nuevo@ejemplo.com'})
        self.assertContains(r, 'Revisa tu correo')
        self.assertEqual(len(mail.outbox), 1)
        # Un correo que no existe recibe el mismo mensaje, pero no se envía nada
        r = self.client.post('/reenviar-activacion/', {'email': 'nadie@ejemplo.com'})
        self.assertContains(r, 'Revisa tu correo')
        self.assertEqual(len(mail.outbox), 1)

    def test_hay_que_aceptar_los_terminos(self):
        r = self.client.post('/registro/', {'username': 'x', 'email': 'x@ejemplo.com',
                                            'password1': CLAVE, 'password2': CLAVE})
        self.assertContains(r, 'Debes aceptar para crear tu cuenta')
        self.assertFalse(Usuario.objects.filter(username='x').exists())

    def test_si_falla_el_envio_se_puede_reintentar(self):
        from unittest import mock
        with mock.patch('apuestas.views.enviar_activacion', side_effect=OSError('sin conexión')):
            r = self.registrar()
        self.assertContains(r, 'No pudimos enviar el correo')
        self.assertFalse(Usuario.objects.filter(username='nuevo').exists())


class RecuperarClaveTests(TestCase):
    def setUp(self):
        self.ana = Usuario.objects.create_user('ana', email='ana@ejemplo.com', password='vieja-clave-123',
                                               email_verificado=True)

    def test_recuperar_contrasena(self):
        r = self.client.post('/recuperar/', {'email': 'ana@ejemplo.com'}, follow=True)
        self.assertContains(r, 'Revisa tu correo')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Crea tu nueva contraseña', mail.outbox[0].subject)
        enlace = enlace_del_correo(mail.outbox[0])
        r = self.client.get(enlace, follow=True)           # Django redirige a una URL con "set-password"
        self.assertContains(r, 'Nueva contraseña')
        r = self.client.post(r.redirect_chain[-1][0], {'new_password1': 'nueva-clave-456',
                                                       'new_password2': 'nueva-clave-456'}, follow=True)
        self.assertContains(r, 'Contraseña cambiada')
        self.ana.refresh_from_db()
        self.assertTrue(self.ana.check_password('nueva-clave-456'))

    def test_no_envia_a_correos_sin_confirmar(self):
        Usuario.objects.filter(pk=self.ana.pk).update(email_verificado=False)
        self.client.post('/recuperar/', {'email': 'ana@ejemplo.com'})
        self.assertEqual(len(mail.outbox), 0)

    def test_el_login_ofrece_recuperar(self):
        self.assertContains(self.client.get('/entrar/'), '¿Olvidaste tu contraseña?')


class CorreoYClaveEnCuentaTests(TestCase):
    def setUp(self):
        self.ana = Usuario.objects.create_user('ana', password='vieja-clave-123')   # cuenta antigua, sin correo
        self.client.force_login(self.ana)

    def test_agregar_y_confirmar_correo(self):
        r = self.client.post('/cuenta/', {'accion': 'correo', 'email': 'Ana@Ejemplo.com'}, follow=True)
        self.assertContains(r, 'Te enviamos un enlace')
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.email, 'ana@ejemplo.com')
        self.assertFalse(self.ana.email_verificado)
        r = self.client.get(enlace_del_correo(mail.outbox[0]), follow=True)
        self.assertContains(r, 'Confirmamos tu correo')
        self.ana.refresh_from_db()
        self.assertTrue(self.ana.email_verificado)

    def test_no_puede_usar_correo_de_otro(self):
        Usuario.objects.create_user('beto', email='beto@ejemplo.com', password='x')
        r = self.client.post('/cuenta/', {'accion': 'correo', 'email': 'beto@ejemplo.com'})
        self.assertContains(r, 'Ya hay una cuenta con ese correo')

    def test_cambiar_contrasena(self):
        r = self.client.post('/cuenta/clave/', {'old_password': 'vieja-clave-123', 'new_password1': 'nueva-clave-456',
                                                'new_password2': 'nueva-clave-456'}, follow=True)
        self.assertContains(r, 'Cambiamos tu contraseña')
        self.ana.refresh_from_db()
        self.assertTrue(self.ana.check_password('nueva-clave-456'))
