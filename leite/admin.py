"""
leite/admin.py
==============
Painel técnico (/ADMIN_URL). O uso diário é pelas telas do sistema;
aqui é só para consulta e suporte. Pagamentos são SOMENTE LEITURA (histórico).
"""

from django.contrib import admin

from .models import Coleta, PagamentoProdutor, Produtor


@admin.register(Produtor)
class ProdutorAdmin(admin.ModelAdmin):
    list_display = ["nome", "apelido_propriedade", "telefone", "preco_litro", "ativo"]
    list_filter = ["ativo"]
    search_fields = ["nome", "apelido_propriedade", "cpf"]


@admin.register(Coleta)
class ColetaAdmin(admin.ModelAdmin):
    list_display = ["data", "produtor", "litros", "preco_litro", "forma", "usuario"]
    list_filter = ["forma", "data"]
    search_fields = ["produtor__nome"]
    date_hierarchy = "data"
    readonly_fields = ["usuario", "criado_em", "atualizado_em"]


@admin.register(PagamentoProdutor)
class PagamentoProdutorAdmin(admin.ModelAdmin):
    list_display = ["data", "produtor", "valor", "forma_pagamento", "estornado"]
    list_filter = ["estornado", "forma_pagamento"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
