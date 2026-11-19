"""
config/urls.py
==============
Mapa principal de endereços (URLs) do sistema.
Cada app tem o seu próprio urls.py; aqui só "penduramos" cada um num prefixo.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Laticínio - Administração técnica"
admin.site.site_title = "Laticínio"

urlpatterns = [
    # O /admin/ padrão NÃO existe: o painel técnico fica no endereço definido no .env (ADMIN_URL).
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("core.urls")),
    path("contas/", include("contas.urls")),
    path("leite/", include("leite.urls")),
    path("financeiro/", include("financeiro.urls")),
    path("backup/", include("backup.urls")),
]

# Páginas de erro personalizadas (funcionam com DEBUG=False).
handler403 = "core.views.erro_403"
handler404 = "core.views.erro_404"
handler500 = "core.views.erro_500"
