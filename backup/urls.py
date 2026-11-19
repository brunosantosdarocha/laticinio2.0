"""backup/urls.py (prefixo /backup/)."""

from django.urls import path

from . import views

app_name = "backup"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("enviar/", views.enviar, name="enviar"),
    path("baixar/", views.baixar_novo, name="baixar_novo"),
    path("arquivo/<str:nome>/", views.baixar_arquivo, name="baixar_arquivo"),
]
