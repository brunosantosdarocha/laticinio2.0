"""
core/validadores.py
===================
Validadores brasileiros reaproveitados em todo o sistema (CPF, CNPJ e telefone).

Cada validador:
- recebe o texto digitado;
- levanta ValidationError com uma mensagem amigável se estiver errado.

As funções "formatar_*" devolvem o texto padronizado (ex.: 123.456.789-09)
e são usadas nos métodos clean_<campo> dos formulários.
"""

import re

from django.core.exceptions import ValidationError


def somente_digitos(texto):
    """Remove tudo que não for número. Ex.: '(27) 99999-0000' -> '27999990000'."""
    return re.sub(r"\D", "", texto or "")


# ------------------------------------------------------------------------------
# CPF
# ------------------------------------------------------------------------------
def cpf_valido(cpf):
    """Confere os dois dígitos verificadores do CPF. Retorna True ou False."""
    numeros = somente_digitos(cpf)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    for posicao in (9, 10):
        soma = sum(int(numeros[i]) * (posicao + 1 - i) for i in range(posicao))
        digito = (soma * 10) % 11 % 10
        if digito != int(numeros[posicao]):
            return False
    return True


def validar_cpf(valor):
    """Validador para usar em campos de formulário/model."""
    if valor and not cpf_valido(valor):
        raise ValidationError("CPF inválido. Confira os números digitados.")


def formatar_cpf(valor):
    """Devolve o CPF no formato 000.000.000-00."""
    n = somente_digitos(valor)
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}" if len(n) == 11 else valor


# ------------------------------------------------------------------------------
# CNPJ (usado nos dados do laticínio)
# ------------------------------------------------------------------------------
def cnpj_valido(cnpj):
    """Confere os dígitos verificadores do CNPJ."""
    n = somente_digitos(cnpj)
    if len(n) != 14 or n == n[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, posicao in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(n[i]) * pesos[i] for i in range(posicao))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(n[posicao]):
            return False
    return True


def validar_cpf_ou_cnpj(valor):
    """Aceita CPF (11 dígitos) ou CNPJ (14 dígitos)."""
    n = somente_digitos(valor)
    if not valor:
        return
    if len(n) == 11 and cpf_valido(n):
        return
    if len(n) == 14 and cnpj_valido(n):
        return
    raise ValidationError("CPF/CNPJ inválido. Confira os números digitados.")


def formatar_cpf_ou_cnpj(valor):
    n = somente_digitos(valor)
    if len(n) == 14:
        return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"
    return formatar_cpf(valor)


# ------------------------------------------------------------------------------
# Telefone com DDD
# ------------------------------------------------------------------------------
def validar_telefone(valor):
    """Telefone brasileiro com DDD: 10 dígitos (fixo) ou 11 (celular começando com 9)."""
    if not valor:
        return
    n = somente_digitos(valor)
    if n.startswith("55") and len(n) in (12, 13):
        n = n[2:]
    if len(n) not in (10, 11) or n[0] == "0":
        raise ValidationError("Telefone inválido. Use o DDD + número, ex.: (27) 99999-0000.")
    if len(n) == 11 and n[2] != "9":
        raise ValidationError("Celular com 11 dígitos deve começar com 9 depois do DDD.")


def formatar_telefone(valor):
    """Devolve (27) 99999-0000 ou (27) 3333-0000."""
    n = somente_digitos(valor)
    if n.startswith("55") and len(n) in (12, 13):
        n = n[2:]
    if len(n) == 11:
        return f"({n[:2]}) {n[2:7]}-{n[7:]}"
    if len(n) == 10:
        return f"({n[:2]}) {n[2:6]}-{n[6:]}"
    return valor
