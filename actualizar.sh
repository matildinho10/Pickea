#!/bin/bash
# Actualiza la página en PythonAnywhere con lo último que hay en GitHub.
# Uso (en una consola Bash de PythonAnywhere):  ~/pickea/actualizar.sh
set -e    # si un paso falla, se detiene y no sigue

cd ~/pickea
source .venv/bin/activate
git pull
pip install -q -r requirements.txt

# Los comandos corren con la misma configuración que la página en internet
# (modo seguro). Si no, collectstatic no crea el índice de archivos con versión.
export DJANGO_DEBUG=0
export DJANGO_SECRET_KEY="$(cat ~/.pickea_secret)"
export DJANGO_ALLOWED_HOSTS=matildinho.pythonanywhere.com

python manage.py respaldar        # copia de seguridad antes de cambiar nada
python manage.py migrate
python manage.py collectstatic --noinput
touch /var/www/matildinho_pythonanywhere_com_wsgi.py   # equivale al botón "Reload"

echo "Listo: la página ya está actualizada. Espera unos 10 segundos antes de abrirla."
