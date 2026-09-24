"""Direcciones de la página: qué vista responde a cada URL."""
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('', views.ranking, name='ranking'),
    path('partidos/', views.partidos, name='partidos'),
    path('apostar/', views.apostar, name='apostar'),
    path('mis-apuestas/', views.mis_apuestas, name='mis_apuestas'),
    path('u/<str:username>/', views.perfil, name='perfil'),
    path('u/<str:username>/seguir/', views.seguir, name='seguir'),
    path('cuenta/', views.cuenta, name='cuenta'),
    path('mi-perfil/', views.mi_perfil, name='mi_perfil'),
    path('como-funciona/', views.como_funciona, name='como_funciona'),
    path('registro/', views.registro, name='registro'),
    path('entrar/', views.EntrarView.as_view(), name='entrar'),
    path('salir/', auth_views.LogoutView.as_view(), name='salir'),
]
