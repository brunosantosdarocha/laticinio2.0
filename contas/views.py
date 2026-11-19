"""
contas/views.py
===============
Login, logout, troca de senha, usuários e níveis de acesso.

- Login e logout são as únicas telas sem login obrigatório (@login_not_required).
- Logout só por POST (um link <a> não consegue deslogar ninguém sem querer).
- Usuários e níveis: somente Administrador.
"""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.utils import termo_busca

from . import servicos
from .decoradores import somente_administrador
from .forms import LoginForm, NivelForm, TrocarSenhaForm, UsuarioCriarForm, UsuarioEditarForm
from .models import Perfil
from .permissoes import ACOES_SIMPLES, MODULOS

logger = logging.getLogger("laticinio")


@login_not_required
def entrar(request):
    """Tela de login. O django-axes conta as tentativas erradas e bloqueia na 5ª."""
    if request.user.is_authenticated:
        return redirect("core:inicio")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.get_user()
        login(request, usuario)
        # O COLETOR (só tem a coleta diária) fica logado por mais tempo: o celular pode passar
        # dias sem internet e a fila offline precisa da sessão para enviar os lançamentos.
        if usuario.has_perm("leite.registrar_coleta_diaria") and not usuario.has_perm("leite.view_coleta"):
            request.session.set_expiry(settings.COLETOR_SESSAO_DIAS * 24 * 60 * 60)
        destino = request.GET.get("next") or ""
        # Evita redirecionar para outro site (open redirect).
        if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
            destino = "core:inicio"
        return redirect(destino)
    return render(request, "contas/login.html", {"form": form})


@require_POST
def sair(request):
    logout(request)
    messages.info(request, "Você saiu do sistema.")
    return redirect("contas:login")


def trocar_senha(request):
    """Troca de senha (obrigatória só quando o administrador exigir)."""
    perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
    form = TrocarSenhaForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        update_session_auth_hash(request, usuario)  # mantém a pessoa logada
        perfil.deve_trocar_senha = False
        perfil.save(update_fields=["deve_trocar_senha"])
        messages.success(request, "Senha alterada com sucesso!")
        return redirect("core:inicio")
    return render(request, "contas/trocar_senha.html", {"form": form, "obrigatoria": perfil.deve_trocar_senha})


# ------------------------------------------------------------------------------
# Usuários (somente Administrador)
# ------------------------------------------------------------------------------
@somente_administrador
def usuarios_lista(request):
    busca = termo_busca(request)
    usuarios = User.objects.prefetch_related("groups").select_related("perfil").order_by("-is_active", "username")
    if busca:
        usuarios = usuarios.filter(username__icontains=busca) | usuarios.filter(first_name__icontains=busca)
    return render(request, "contas/usuarios_lista.html", {"usuarios": usuarios, "busca": busca})


@somente_administrador
def usuario_criar(request):
    form = UsuarioCriarForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        usuario, senha = servicos.criar_usuario(
            username=d["username"], nome=d["nome"], email=d["email"], nivel=d["nivel"], administrador=d["administrador"],
            exigir_troca=d["exigir_troca"],
        )
        # A senha aparece UMA vez só, nesta resposta. Não fica gravada em lugar nenhum.
        return render(request, "contas/senha_provisoria.html", {"usuario": usuario, "senha": senha})
    return render(request, "contas/usuario_form.html", {"form": form, "titulo": "Novo usuário"})


@somente_administrador
def usuario_editar(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    inicial = {
        "nome": usuario.first_name, "email": usuario.email, "nivel": usuario.groups.first(),
        "administrador": usuario.is_superuser, "ativo": usuario.is_active,
        "exigir_troca": getattr(getattr(usuario, "perfil", None), "deve_trocar_senha", False),
    }
    form = UsuarioEditarForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            servicos.atualizar_usuario(
                usuario, editor=request.user, nome=d["nome"], email=d["email"], nivel=d["nivel"],
                administrador=d["administrador"], ativo=d["ativo"], exigir_troca=d["exigir_troca"],
            )
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
        else:
            messages.success(request, "Usuário atualizado.")
            return redirect("contas:usuarios")
    return render(request, "contas/usuario_form.html", {
        "form": form, "titulo": f"Editar usuário: {usuario.username}", "usuario_editado": usuario,
    })


@require_POST
@somente_administrador
def usuario_redefinir_senha(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    senha = servicos.redefinir_senha(usuario)
    return render(request, "contas/senha_provisoria.html", {"usuario": usuario, "senha": senha, "redefinida": True})


@require_POST
@somente_administrador
def usuario_desbloquear(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    servicos.desbloquear(usuario)
    messages.success(request, f"Usuário {usuario.username} desbloqueado.")
    return redirect("contas:usuarios")


# ------------------------------------------------------------------------------
# Níveis de acesso (somente Administrador)
# ------------------------------------------------------------------------------
@somente_administrador
def niveis_lista(request):
    return render(request, "contas/niveis_lista.html", {"niveis": Group.objects.prefetch_related("user_set")})


def _tabela_permissoes(grupo):
    """Monta a tabela módulos x ações para o template, marcando o que o nível já tem."""
    atuais = set()
    if grupo is not None and grupo.pk:
        atuais = {f"{p.content_type.app_label}.{p.codename}" for p in grupo.permissions.select_related("content_type")}
    linhas = []
    for modulo in MODULOS:
        celulas = []
        for acao in ACOES_SIMPLES:
            codename = modulo["acoes"].get(acao)
            codigo = f"{modulo['app']}.{codename}" if codename else None
            celulas.append({"codigo": codigo, "marcado": codigo in atuais})
        especiais = [
            {"codigo": f"{modulo['app']}.{c}", "rotulo": r, "marcado": f"{modulo['app']}.{c}" in atuais}
            for c, r in modulo["acoes"].get("especial", [])
        ]
        linhas.append({"nome": modulo["nome"], "celulas": celulas, "especiais": especiais})
    return linhas


@somente_administrador
def nivel_editar(request, pk=None):
    grupo = get_object_or_404(Group, pk=pk) if pk else None
    form = NivelForm(request.POST or None, instance=grupo)
    if request.method == "POST" and form.is_valid():
        grupo = form.save()
        servicos.salvar_permissoes_nivel(grupo, request.POST.getlist("permissoes"))
        messages.success(request, f"Nível '{grupo.name}' salvo.")
        return redirect("contas:niveis")
    return render(request, "contas/nivel_form.html", {
        "form": form, "grupo": grupo, "linhas": _tabela_permissoes(grupo), "acoes": ["Ver", "Criar", "Editar", "Excluir"],
    })
