"""
core/context_processors.py
==========================
Variáveis disponíveis em TODOS os templates:
- nome_empresa: aparece no menu e no título;
- alertas: itens do sininho (só para usuários logados).
"""

from .models import DadosEmpresa
from .servicos import alertas_do_usuario


def sistema(request):
    contexto = {"nome_empresa": "Laticínio"}
    try:
        contexto["nome_empresa"] = DadosEmpresa.obter().nome
    except Exception:  # banco ainda não migrado (primeira execução)
        return contexto
    usuario = getattr(request, "user", None)
    if usuario is not None and usuario.is_authenticated:
        contexto["alertas"] = alertas_do_usuario(usuario)
    return contexto
