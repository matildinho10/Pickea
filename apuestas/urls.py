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
    path('registro/', views.registro, name='registro'),
    path('entrar/', auth_views.LoginView.as_view(template_name='apuestas/entrar.html'), name='entrar'),
    path('salir/', auth_views.LogoutView.as_view(), name='salir'),
]
