"""Formularios: definen qué campos se piden y cómo se validan."""
from django.contrib.auth.forms import UserCreationForm

from .models import Usuario


class RegistroForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ['username']
        labels = {'username': 'Nombre de usuario'}
        help_texts = {'username': 'Así aparecerás en el ranking. Letras, números y @ . + - _'}
