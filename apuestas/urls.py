"""Direcciones de la página: qué vista responde a cada URL."""
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import RecuperarForm

urlpatterns = [
    path('', views.ranking, name='ranking'),
    path('partidos/', views.partidos, name='partidos'),
    path('apostar/', views.apostar, name='apostar'),
    path('mis-apuestas/', views.mis_apuestas, name='mis_apuestas'),
    path('u/<str:username>/', views.perfil, name='perfil'),
    path('u/<str:username>/seguir/', views.seguir, name='seguir'),
    path('cuenta/', views.cuenta, name='cuenta'),
    path('cuenta/borrar/', views.borrar_cuenta, name='borrar_cuenta'),
    path('siguiendo/', views.siguiendo, name='siguiendo'),
    path('terminos/', views.terminos, name='terminos'),
    path('privacidad/', views.privacidad, name='privacidad'),
    path('mi-perfil/', views.mi_perfil, name='mi_perfil'),
    path('como-funciona/', views.como_funciona, name='como_funciona'),
    path('registro/', views.registro, name='registro'),
    path('activar/<uidb64>/<codigo>/', views.activar, name='activar'),
    path('reenviar-activacion/', views.reenviar_activacion, name='reenviar_activacion'),
    path('confirmar-correo/<uidb64>/<codigo>/', views.confirmar_correo, name='confirmar_correo'),
    path('cuenta/clave/', views.CambiarClaveView.as_view(), name='cambiar_clave'),

    # Recuperar contraseña (vistas de Django con nuestras plantillas)
    path('recuperar/', auth_views.PasswordResetView.as_view(
        form_class=RecuperarForm,
        template_name='apuestas/recuperar.html',
        email_template_name='apuestas/correos/recuperar.txt',
        html_email_template_name='apuestas/correos/recuperar.html',
        subject_template_name='apuestas/correos/recuperar_asunto.txt',
        extra_email_context={'NOMBRE_SITIO': settings.NOMBRE_SITIO},
        success_url=reverse_lazy('recuperar_enviado')), name='recuperar'),
    path('recuperar/enviado/', auth_views.PasswordResetDoneView.as_view(
        template_name='apuestas/aviso.html',
        extra_context={'titulo': 'Revisa tu correo', 'entrar': True,
                       'mensaje': 'Si ese correo está confirmado en una cuenta, te enviamos un enlace para crear '
                                  'una contraseña nueva. Revisa también la carpeta de spam.'}),
        name='recuperar_enviado'),
    path('recuperar/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='apuestas/nueva_clave.html',
        success_url=reverse_lazy('recuperar_listo')), name='recuperar_confirmar'),
    path('recuperar/listo/', auth_views.PasswordResetCompleteView.as_view(
        template_name='apuestas/aviso.html',
        extra_context={'titulo': 'Contraseña cambiada', 'entrar': True,
                       'mensaje': 'Ya puedes entrar con tu nueva contraseña.'}),
        name='recuperar_listo'),
    path('entrar/', views.EntrarView.as_view(), name='entrar'),
    path('salir/', auth_views.LogoutView.as_view(), name='salir'),
]
