"""
core/utils.py
=============
Funções pequenas e reaproveitáveis (ajudantes) usadas por várias telas:
- estilizar_campos: coloca as classes do Bootstrap nos campos do formulário;
- paginar: divide listas grandes em páginas;
- termo_busca: lê o texto da busca com limite de tamanho;
- funções de datas (primeiro/último dia do mês, últimos meses);
- dinheiro: arredonda valores para centavos;
- link_whatsapp: monta o link wa.me com o texto pronto.
"""

import calendar
import datetime
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote

from django import forms
from django.core.paginator import Paginator

from .validadores import somente_digitos

CENTAVOS = Decimal("0.01")


def dinheiro(valor):
    """Arredonda um valor para 2 casas (centavos) do jeito comercial (0,005 -> 0,01)."""
    if valor is None:
        return Decimal("0.00")
    return Decimal(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def estilizar_campos(form):
    """Aplica as classes do Bootstrap 5 em todos os campos de um formulário.

    Assim não precisamos repetir 'class="form-control"' em cada template.
    """
    for nome, campo in form.fields.items():
        widget = campo.widget
        classes = widget.attrs.get("class", "")
        if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect, forms.CheckboxSelectMultiple)):
            novo = "form-check-input"
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            novo = "form-select"
        else:
            novo = "form-control"
        if novo and novo not in classes:
            widget.attrs["class"] = (classes + " " + novo).strip()
        # Datas com o calendário nativo do navegador
        if isinstance(widget, forms.DateInput):
            widget.input_type = "date"
            widget.format = "%Y-%m-%d"
        if isinstance(widget, forms.TimeInput):
            widget.input_type = "time"
            widget.format = "%H:%M"
    return form


def paginar(request, consulta, por_pagina=20):
    """Divide uma consulta em páginas. A página atual vem de ?pagina=N na URL."""
    paginador = Paginator(consulta, por_pagina)
    return paginador.get_page(request.GET.get("pagina"))


def termo_busca(request, nome="q"):
    """Lê o termo de busca da URL, sem espaços sobrando e com no máximo 100 caracteres."""
    return (request.GET.get(nome) or "").strip()[:100]


def primeiro_dia_mes(data):
    return data.replace(day=1)


def ultimo_dia_mes(data):
    return data.replace(day=calendar.monthrange(data.year, data.month)[1])


def ultimos_meses(quantidade, referencia=None):
    """Lista (ano, mes) dos últimos N meses, do mais antigo para o mais novo."""
    referencia = referencia or datetime.date.today()
    ano, mes = referencia.year, referencia.month
    meses = []
    for _ in range(quantidade):
        meses.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes, ano = 12, ano - 1
    return list(reversed(meses))


def ler_data(texto, padrao=None):
    """Converte '2026-11-15' em date. Se vier vazio ou errado, devolve o padrão."""
    try:
        return datetime.date.fromisoformat((texto or "").strip())
    except ValueError:
        return padrao


def ler_inteiro(texto, padrao, minimo=None, maximo=None):
    """Converte texto em inteiro dentro de um intervalo; se falhar usa o padrão."""
    try:
        valor = int(texto)
    except (TypeError, ValueError):
        return padrao
    if (minimo is not None and valor < minimo) or (maximo is not None and valor > maximo):
        return padrao
    return valor


def link_whatsapp(telefone, texto):
    """Monta o link https://wa.me/55DDDNUMERO?text=... (abre o WhatsApp com a mensagem pronta)."""
    numero = somente_digitos(telefone)
    if not numero:
        return ""
    if not numero.startswith("55"):
        numero = "55" + numero
    return f"https://wa.me/{numero}?text={quote(texto)}"
