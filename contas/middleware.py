"""
contas/middleware.py
====================
Middleware em forma de FUNÇÃO que obriga o usuário a trocar a senha provisória.

Enquanto perfil.deve_trocar_senha for True, qualquer página redireciona para
"Alterar senha" (menos a própria tela, o logout e os arquivos estáticos).
"""

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse


def forcar_troca_de_senha(get_response):
    """Recebe a próxima "camada" e devolve a função que trata cada requisição."""

    def middleware(request):
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated:
            perfil = getattr(usuario, "perfil", None)
            if perfil is not None and perfil.deve_trocar_senha:
                liberados = (reverse("contas:trocar_senha"), reverse("contas:logout"))
                caminho = request.path
                if caminho not in liberados and not caminho.startswith("/" + settings.STATIC_URL.lstrip("/")):
                    # A fila offline do celular recebe JSON (e não um redirecionamento).
                    if caminho.startswith("/leite/api/"):
                        return JsonResponse({"erro": "Troque a senha provisória antes de enviar."}, status=403)
                    return redirect("contas:trocar_senha")
        return get_response(request)

    return middleware
