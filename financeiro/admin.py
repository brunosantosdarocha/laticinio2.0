"""
financeiro/admin.py
===================
Painel técnico. Lançamentos são SOMENTE LEITURA: erro se corrige com estorno pela tela do sistema.
"""

from django.contrib import admin

from .models import Categoria, Lancamento


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nome", "tipo", "ativa", "sistema"]
    list_filter = ["tipo", "ativa"]


@admin.register(Lancamento)
class LancamentoAdmin(admin.ModelAdmin):
    list_display = ["data", "tipo", "categoria", "valor", "estornado", "usuario"]
    list_filter = ["tipo", "estornado", "categoria"]
    date_hierarchy = "data"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
