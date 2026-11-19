"""backup/admin.py - histórico de backups somente leitura."""

from django.contrib import admin

from .models import RegistroBackup


@admin.register(RegistroBackup)
class RegistroBackupAdmin(admin.ModelAdmin):
    list_display = ["criado_em", "arquivo", "origem", "sucesso", "enviado_para"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
