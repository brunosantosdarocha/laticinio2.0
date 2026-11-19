"""
core/views.py
=============
- inicio: dashboard (ou manda o Coletor direto para a página de coleta diária);
- empresa: dados do laticínio;
- erro_403/404/500: páginas de erro personalizadas.
"""

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.shortcuts import redirect, render

from .forms import DadosEmpresaForm
from .models import DadosEmpresa
from .servicos import dados_dashboard


def inicio(request):
    """Página inicial. Cada nível de acesso cai na tela que faz sentido para ele."""
    usuario = request.user
    if usuario.has_perm("leite.view_coleta"):
        return render(request, "core/dashboard.html", dados_dashboard(usuario))
    if usuario.has_perm("leite.registrar_coleta_diaria"):
        return redirect("leite:coleta_diaria")
    if usuario.has_perm("financeiro.view_lancamento"):
        return redirect("financeiro:extrato")
    return render(request, "core/sem_modulos.html")


@permission_required("core.view_dadosempresa", raise_exception=True)
def empresa(request):
    dados = DadosEmpresa.obter()
    pode_editar = request.user.has_perm("core.change_dadosempresa")
    form = DadosEmpresaForm(request.POST or None, instance=dados)
    if not pode_editar:
        for campo in form.fields.values():
            campo.disabled = True
    if request.method == "POST" and pode_editar and form.is_valid():
        form.save()
        messages.success(request, "Dados do laticínio atualizados.")
        return redirect("core:empresa")
    return render(request, "core/empresa_form.html", {"form": form, "pode_editar": pode_editar})


# ------------------------------------------------------------------------------
# Páginas de erro. Para quem não está logado, mostramos a versão sem o menu.
# ------------------------------------------------------------------------------
def _template_erro(request, codigo):
    logado = getattr(request, "user", None) is not None and request.user.is_authenticated
    return f"erros/{codigo}.html" if logado else "erros/simples.html"


def erro_403(request, exception=None):
    return render(request, _template_erro(request, 403), {
        "codigo": 403, "titulo": "Acesso negado", "mensagem": "Seu nível de acesso não permite abrir esta página.",
    }, status=403)


def erro_404(request, exception=None):
    return render(request, _template_erro(request, 404), {
        "codigo": 404, "titulo": "Página não encontrada", "mensagem": "O endereço não existe ou o registro foi removido.",
    }, status=404)


def erro_500(request):
    # Página simples, sem consultas ao banco (o erro pode ser justamente no banco).
    return render(request, "erros/simples.html", {
        "codigo": 500, "titulo": "Erro interno", "mensagem": "Algo deu errado. Tente novamente; se continuar, avise o suporte.",
    }, status=500)
