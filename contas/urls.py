"""contas/urls.py - login, senha, usuários e níveis (prefixo /contas/)."""

from django.urls import path

from . import views

app_name = "contas"

urlpatterns = [
    path("entrar/", views.entrar, name="login"),
    path("sair/", views.sair, name="logout"),
    path("senha/", views.trocar_senha, name="trocar_senha"),
    path("usuarios/", views.usuarios_lista, name="usuarios"),
    path("usuarios/novo/", views.usuario_criar, name="usuario_criar"),
    path("usuarios/<int:pk>/editar/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/<int:pk>/redefinir-senha/", views.usuario_redefinir_senha, name="usuario_redefinir_senha"),
    path("usuarios/<int:pk>/desbloquear/", views.usuario_desbloquear, name="usuario_desbloquear"),
    path("niveis/", views.niveis_lista, name="niveis"),
    path("niveis/novo/", views.nivel_editar, name="nivel_criar"),
    path("niveis/<int:pk>/editar/", views.nivel_editar, name="nivel_editar"),
]
