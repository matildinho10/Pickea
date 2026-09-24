"""Formularios: definen qué campos se piden y cómo se validan."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, UserCreationForm
from django.core.exceptions import ValidationError

from .fotos import MAXIMO_MB
from .models import Usuario


def correo_disponible(email, excepto=None):
    """Cada correo puede estar en una sola cuenta."""
    ocupado = Usuario.objects.filter(email__iexact=email)
    if excepto is not None:
        ocupado = ocupado.exclude(pk=excepto.pk)
    if ocupado.exists():
        raise ValidationError('Ya hay una cuenta con ese correo.')
    return email.lower()


class RegistroForm(UserCreationForm):
    email = forms.EmailField(label='Correo', help_text='Te enviaremos un enlace para activar tu cuenta.')

    class Meta:
        model = Usuario
        fields = ['username', 'email']
        labels = {'username': 'Nombre de usuario'}
        help_texts = {'username': 'Así aparecerás en el ranking. Letras, números y @ . + - _'}

    def clean_email(self):
        return correo_disponible(self.cleaned_data['email'])


class EntrarForm(AuthenticationForm):
    """Como el de Django, pero avisa si la cuenta existe y todavía no se activó."""
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Nombre de usuario o contraseña incorrectos.',
        'inactive': 'Tu cuenta todavía no está activada. Revisa tu correo (también la carpeta de spam).',
    }

    def clean(self):
        try:
            return super().clean()
        except ValidationError:
            usuario = Usuario.objects.filter(username=self.cleaned_data.get('username')).first()
            if usuario and not usuario.is_active and usuario.check_password(self.cleaned_data.get('password') or ''):
                self.cuenta_sin_activar = True
                raise ValidationError(self.error_messages['inactive'], code='inactive')
            raise


class CorreoForm(forms.Form):
    email = forms.EmailField(label='Correo')

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_email(self):
        return correo_disponible(self.cleaned_data['email'], excepto=self.usuario)


class ReenviarForm(forms.Form):
    email = forms.EmailField(label='Correo con el que te registraste')


class RecuperarForm(PasswordResetForm):
    """Solo envía el enlace a correos confirmados (así nadie recupera una cuenta con un correo ajeno)."""

    def get_users(self, email):
        return (u for u in super().get_users(email) if u.email_verificado)


class FotoForm(forms.Form):
    foto = forms.ImageField(label='Nueva foto', help_text=f'JPG, PNG o WEBP, hasta {MAXIMO_MB} MB.')

    def clean_foto(self):
        foto = self.cleaned_data['foto']
        if foto.size > MAXIMO_MB * 1024 * 1024:
            raise forms.ValidationError(f'La foto pesa más de {MAXIMO_MB} MB.')
        return foto
