"""
core/templatetags/formatos.py
=============================
Filtros de template para mostrar números no padrão brasileiro.

Uso no template:
    {% load formatos %}
    {{ valor|moeda }}    -> R$ 1.234,56
    {{ litros|litros }}  -> 1.234,5 L
    {{ numero|numero_br:2 }} -> 1.234,56
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def _formatar(valor, casas):
    """Formata um número com ponto no milhar e vírgula nos decimais."""
    try:
        numero = Decimal(str(valor if valor is not None else 0))
    except (InvalidOperation, ValueError):
        return str(valor)
    texto = f"{numero:,.{casas}f}"  # ex.: 1,234.56 (padrão americano)
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


@register.filter
def moeda(valor):
    """Valor em reais: R$ 1.234,56 (negativo vira -R$ 10,00)."""
    texto = _formatar(valor, 2)
    if texto.startswith("-"):
        return "-R$ " + texto[1:]
    return "R$ " + texto


@register.filter
def litros(valor):
    """Quantidade de leite: 1.234,5 L."""
    return _formatar(valor, 1) + " L"


@register.filter
def numero_br(valor, casas=2):
    """Número com N casas no padrão brasileiro."""
    return _formatar(valor, int(casas))


@register.filter
def obter(dicionario, chave):
    """Lê dicionario[chave] dentro do template (o Django não faz isso sozinho)."""
    try:
        return dicionario.get(chave)
    except AttributeError:
        return None
