"""leite/urls.py - endereços das telas do leite (prefixo /leite/)."""

from django.urls import path

from . import views

app_name = "leite"

urlpatterns = [
    path("coleta-diaria/", views.coleta_diaria, name="coleta_diaria"),
    path("coleta-diaria/sw.js", views.service_worker, name="service_worker"),
    path("coleta-diaria/manifest.webmanifest", views.manifest, name="manifest"),
    path("api/coleta/estado/", views.api_coleta_estado, name="api_coleta_estado"),
    path("api/coleta/sincronizar/", views.api_coleta_sincronizar, name="api_coleta_sincronizar"),
    path("produtores/", views.produtores_lista, name="produtores"),
    path("produtores/novo/", views.produtor_criar, name="produtor_criar"),
    path("produtores/<int:pk>/", views.produtor_detalhe, name="produtor_detalhe"),
    path("produtores/<int:pk>/editar/", views.produtor_editar, name="produtor_editar"),
    path("produtores/<int:pk>/excluir/", views.produtor_excluir, name="produtor_excluir"),
    path("produtores/<int:produtor_pk>/pagar/", views.pagamento_novo, name="pagamento_novo"),
    path("calendario/", views.calendario, name="calendario"),
    path("calendario/preco-em-massa/", views.preco_massa, name="preco_massa"),
    path("coletas/<int:pk>/editar/", views.coleta_editar, name="coleta_editar"),
    path("coletas/<int:pk>/excluir/", views.coleta_excluir, name="coleta_excluir"),
    path("recibo/", views.recibo, name="recibo"),
    path("recibo/imprimir/", views.recibo_imprimir, name="recibo_imprimir"),
    path("recibo/pdf/", views.recibo_pdf, name="recibo_pdf"),
    path("saldos/", views.saldos, name="saldos"),
    path("pagamentos/", views.pagamentos_lista, name="pagamentos"),
    path("pagamentos/<int:pk>/estornar/", views.pagamento_estornar, name="pagamento_estornar"),
]
