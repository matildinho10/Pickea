"""
Cambia el nombre de un usuario (sus apuestas, seguidores y foto se mantienen).

Uso:  python manage.py renombrar_usuario nombre_actual nombre_nuevo
"""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apuestas.models import Usuario


class Command(BaseCommand):
    help = 'Cambia el nombre de un usuario.'

    def add_arguments(self, parser):
        parser.add_argument('actual')
        parser.add_argument('nuevo')

    def handle(self, *args, **opts):
        actual, nuevo = opts['actual'], opts['nuevo']
        usuario = Usuario.objects.filter(username=actual).first()
        if usuario is None:
            raise CommandError(f'No existe el usuario "{actual}".')
        if Usuario.objects.filter(username__iexact=nuevo).exclude(pk=usuario.pk).exists():
            raise CommandError(f'Ya existe un usuario llamado "{nuevo}".')

        usuario.username = nuevo
        try:
            usuario.full_clean(exclude=['password'])   # mismas reglas que al crear una cuenta
        except ValidationError as e:
            raise CommandError(f'Nombre no válido: {"; ".join(e.messages)}')
        usuario.save(update_fields=['username'])
        self.stdout.write(self.style.SUCCESS(f'Listo: @{actual} ahora se llama @{nuevo}.'))
