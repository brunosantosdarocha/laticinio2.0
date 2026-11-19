"""
contas/servicos.py
==================
Regras de usuários e níveis de acesso (grupos do Django).
"""

import logging
import secrets
import string

from axes.utils import reset as axes_reset
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Perfil
from .permissoes import NIVEIS_PADRAO, codigos_permitidos

logger = logging.getLogger("laticinio")


def gerar_senha_provisoria(tamanho=10):
    """Senha aleatória forte (letras + números), sem caracteres confusos como O/0 e l/1."""
    alfabeto = "".join(c for c in string.ascii_letters + string.digits if c not in "O0Il1")
    while True:
        senha = "".join(secrets.choice(alfabeto) for _ in range(tamanho))
        if any(c.isdigit() for c in senha) and any(c.isalpha() for c in senha):
            return senha


def buscar_permissoes(codigos):
    """Converte ['leite.view_coleta', ...] em objetos Permission (ignora os inexistentes)."""
    permissoes = []
    for codigo in codigos:
        app, codename = codigo.split(".", 1)
        permissao = Permission.objects.filter(content_type__app_label=app, codename=codename).first()
        if permissao:
            permissoes.append(permissao)
    return permissoes


def configurar_grupos_padrao(redefinir=False):
    """Cria os níveis Gerente / Escritório / Coletor.

    Sem redefinir: só cria os que não existem (não mexe no que o administrador já ajustou).
    Com redefinir: volta as permissões dos níveis padrão para o original.
    Devolve a lista de nomes criados/redefinidos.
    """
    alterados = []
    for nome, codigos in NIVEIS_PADRAO.items():
        grupo, criado = Group.objects.get_or_create(name=nome)
        if criado or redefinir:
            grupo.permissions.set(buscar_permissoes(codigos))
            alterados.append(nome)
    return alterados


def salvar_permissoes_nivel(grupo, codigos_marcados):
    """Grava as permissões do nível. Só aceita códigos da lista oficial (interseção)."""
    validos = set(codigos_marcados) & codigos_permitidos()
    # Mantém permissões "de fora da lista" que o grupo já tinha (ex.: dadas pelo admin técnico).
    fora_da_lista = [
        p for p in grupo.permissions.select_related("content_type")
        if f"{p.content_type.app_label}.{p.codename}" not in codigos_permitidos()
    ]
    grupo.permissions.set(buscar_permissoes(validos) + fora_da_lista)
    return validos


def administradores_ativos():
    return User.objects.filter(is_superuser=True, is_active=True)


@transaction.atomic
def criar_usuario(*, username, nome, email, nivel, administrador, exigir_troca=False):
    """Cria o usuário com senha provisória (mostrada uma única vez na tela).
    Só obriga a troca no primeiro acesso se o administrador pedir (exigir_troca=True)."""
    senha = gerar_senha_provisoria()
    usuario = User.objects.create_user(username=username, password=senha, first_name=nome, email=email)
    usuario.is_superuser = bool(administrador)
    usuario.is_staff = bool(administrador)
    usuario.save()
    if nivel:
        usuario.groups.set([nivel])
    Perfil.objects.update_or_create(usuario=usuario, defaults={"deve_trocar_senha": bool(exigir_troca)})
    logger.info("Usuário '%s' criado.", username)
    return usuario, senha


@transaction.atomic
def atualizar_usuario(usuario, *, editor, nome, email, nivel, administrador, ativo, exigir_troca=None):
    """Atualiza nível e situação, com travas para nunca ficar sem administrador."""
    if usuario.pk == editor.pk and (not administrador or not ativo):
        raise ValidationError("Você não pode tirar o seu próprio acesso de administrador nem se desativar.")
    perde_admin = usuario.is_superuser and usuario.is_active and (not administrador or not ativo)
    if perde_admin and administradores_ativos().exclude(pk=usuario.pk).count() == 0:
        raise ValidationError("O sistema precisa ter pelo menos um administrador ativo.")
    usuario.first_name = nome
    usuario.email = email
    usuario.is_superuser = bool(administrador)
    usuario.is_staff = bool(administrador)
    usuario.is_active = bool(ativo)
    usuario.save()
    usuario.groups.set([nivel] if nivel else [])
    if exigir_troca is not None:
        Perfil.objects.update_or_create(usuario=usuario, defaults={"deve_trocar_senha": bool(exigir_troca)})
    return usuario


def redefinir_senha(usuario, exigir_troca=False):
    """Gera nova senha provisória e desbloqueia o usuário.
    A troca no próximo acesso só é exigida se o administrador pedir."""
    senha = gerar_senha_provisoria()
    usuario.set_password(senha)
    usuario.save()
    Perfil.objects.update_or_create(usuario=usuario, defaults={"deve_trocar_senha": bool(exigir_troca)})
    axes_reset(username=usuario.username)
    logger.info("Senha do usuário '%s' redefinida.", usuario.username)
    return senha


def desbloquear(usuario):
    """Libera um usuário bloqueado por excesso de senhas erradas."""
    axes_reset(username=usuario.username)
    logger.info("Usuário '%s' desbloqueado.", usuario.username)
