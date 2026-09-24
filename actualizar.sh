#!/bin/bash
# Actualiza la página en PythonAnywhere con lo último que hay en GitHub.
# Uso (en una consola Bash de PythonAnywhere):  ~/pickea/actualizar.sh
set -e    # si un paso falla, se detiene y no sigue

cd ~/pickea
source .venv/bin/activate
git pull
pip install -q -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
touch /var/www/matildinho_pythonanywhere_com_wsgi.py   # equivale al botón "Reload"

echo "Listo: la página ya está actualizada."
