"""
Correos de la página: activar la cuenta y confirmar un correo nuevo.
(El de "recuperar contraseña" lo envía Django con nuestras plantillas.)

Los enlaces llevan el número de usuario y un código firmado que:
  - vence a los 3 días (PASSWORD_RESET_TIMEOUT),
  - deja de servir apenas se usa (cambia si la cuenta se activa o el correo se confirma),
  - no sirve para cambiar la contraseña (es distinto al de recuperar contraseña).
"""
from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import Usuario


class CodigoDeCorreo(PasswordResetTokenGenerator):
    key_salt = 'apuestas.correos.CodigoDeCorreo'

    def _make_hash_value(self, usuario, timestamp):
        # Al activar la cuenta o confirmar el correo cambian estos datos,
        # así que el mismo enlace ya no vuelve a funcionar.
        return f'{super()._make_hash_value(usuario, timestamp)}{usuario.is_active}{usuario.email_verificado}'


codigo_de_correo = CodigoDeCorreo()


def enlace(request, nombre_url, usuario):
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    codigo = codigo_de_correo.make_token(usuario)
    return request.build_absolute_uri(reverse(nombre_url, args=[uid, codigo]))


def usuario_del_enlace(uidb64, codigo):
    """El usuario del enlace, o None si el enlace es falso, ya se usó o venció."""
    try:
        usuario = Usuario.objects.get(pk=urlsafe_base64_decode(uidb64).decode())
    except (ValueError, TypeError, OverflowError, Usuario.DoesNotExist):
        return None
    return usuario if codigo_de_correo.check_token(usuario, codigo) else None


def enviar(usuario, asunto, plantilla, contexto):
    contexto = {'usuario': usuario, 'NOMBRE_SITIO': settings.NOMBRE_SITIO, **contexto}
    texto = render_to_string(f'apuestas/correos/{plantilla}.txt', contexto)
    html = render_to_string(f'apuestas/correos/{plantilla}.html', contexto)
    correo = EmailMultiAlternatives(f'{asunto} · {settings.NOMBRE_SITIO}', texto, to=[usuario.email])
    correo.attach_alternative(html, 'text/html')
    correo.send()


def enviar_activacion(request, usuario):
    enviar(usuario, 'Activa tu cuenta', 'activacion', {'enlace': enlace(request, 'activar', usuario)})


def enviar_confirmacion(request, usuario):
    enviar(usuario, 'Confirma tu correo', 'confirmar_correo',
           {'enlace': enlace(request, 'confirmar_correo', usuario)})
