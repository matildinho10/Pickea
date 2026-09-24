"""Procesa las fotos de perfil: recorte cuadrado, 256x256, JPG liviano."""
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

TAMANO = 256
MAXIMO_MB = 5


def procesar_foto(archivo):
    """
    Recibe el archivo subido y devuelve un JPG cuadrado de 256x256 listo para guardar.
    Volver a dibujar la imagen desde cero descarta cualquier dato extra del archivo
    original (ubicación GPS, contenido escondido, etc.).
    """
    imagen = Image.open(archivo)
    imagen = ImageOps.exif_transpose(imagen)          # respeta fotos giradas del celular
    imagen = ImageOps.fit(imagen.convert('RGB'), (TAMANO, TAMANO), Image.Resampling.LANCZOS)
    salida = BytesIO()
    imagen.save(salida, format='JPEG', quality=85, optimize=True)
    return ContentFile(salida.getvalue(), name='foto.jpg')
