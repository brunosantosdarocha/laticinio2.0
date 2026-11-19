"""financeiro/urls.py - endereços do caixa (prefixo /financeiro/)."""

from django.urls import path

from . import views

app_name = "financeiro"

urlpatterns = [
    path("", views.extrato, name="extrato"),
    path("novo/<str:tipo>/", views.lancamento_novo, name="lancamento_novo"),
    path("lancamentos/<int:pk>/estornar/", views.lancamento_estornar, name="lancamento_estornar"),
    path("categorias/", views.categorias_lista, name="categorias"),
    path("categorias/nova/", views.categoria_criar, name="categoria_criar"),
    path("categorias/<int:pk>/editar/", views.categoria_editar, name="categoria_editar"),
]
