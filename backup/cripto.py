"""
backup/cripto.py
================
Criptografia da senha do e-mail com Fernet (biblioteca cryptography).

A chave é derivada da SECRET_KEY do .env (SHA-256). Assim:
- quem copiar só o banco de dados NÃO consegue ler a senha;
- se a SECRET_KEY mudar, basta digitar a senha do e-mail de novo na tela de backup.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    chave = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(chave))


def cifrar(texto):
    return _fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def decifrar(texto_cifrado):
    """Devolve a senha original, ou texto vazio se a chave mudou."""
    try:
        return _fernet().decrypt(texto_cifrado.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
