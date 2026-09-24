"""Formularios: definen qué campos se piden y cómo se validan."""
from django import forms
from django.contrib.auth.forms import UserCreationForm

from .fotos import MAXIMO_MB
from .models import Usuario


class RegistroForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ['username']
        labels = {'username': 'Nombre de usuario'}
        help_texts = {'username': 'Así aparecerás en el ranking. Letras, números y @ . + - _'}


class FotoForm(forms.Form):
    foto = forms.ImageField(label='Nueva foto', help_text=f'JPG, PNG o WEBP, hasta {MAXIMO_MB} MB.')

    def clean_foto(self):
        foto = self.cleaned_data['foto']
        if foto.size > MAXIMO_MB * 1024 * 1024:
            raise forms.ValidationError(f'La foto pesa más de {MAXIMO_MB} MB.')
        return foto
