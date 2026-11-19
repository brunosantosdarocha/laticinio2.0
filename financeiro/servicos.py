"""
financeiro/servicos.py
======================
Regras de negócio do caixa. As views só validam o formulário e chamam estas funções.
Quando algo não pode ser feito, a função levanta ValidationError com uma mensagem amigável.
"""

import logging
from collections import OrderedDict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.escolhas import NOMES_MESES
from core.utils import dinheiro, ultimos_meses

from .models import Categoria, Lancamento, TipoLancamento

logger = logging.getLogger("laticinio")

NOME_CATEGORIA_PAGAMENTO_PRODUTOR = "Pagamento a produtores"


def categoria_pagamento_produtor():
    """Categoria de saída usada automaticamente quando se paga um produtor."""
    categoria, _ = Categoria.objects.get_or_create(
        nome=NOME_CATEGORIA_PAGAMENTO_PRODUTOR,
        tipo=TipoLancamento.SAIDA,
        defaults={"sistema": True},
    )
    return categoria


def criar_lancamento(*, tipo, categoria, valor, data, descricao="", forma_pagamento="", usuario=None):
    """Grava uma entrada ou saída no caixa, conferindo as regras básicas."""
    valor = dinheiro(valor)
    if valor <= 0:
        raise ValidationError("Informe um valor maior que zero.")
    if categoria.tipo != tipo:
        raise ValidationError("A categoria escolhida não é do tipo deste lançamento.")
    if not categoria.ativa:
        raise ValidationError("Esta categoria está desativada.")
    lancamento = Lancamento.objects.create(
        tipo=tipo, categoria=categoria, valor=valor, data=data,
        descricao=descricao, forma_pagamento=forma_pagamento, usuario=usuario,
    )
    return lancamento


@transaction.atomic
def estornar_lancamento(lancamento, *, motivo, usuario, permitir_vinculado=False):
    """Marca o lançamento como estornado (ele sai dos totais, mas continua no histórico).

    Lançamentos gerados por um pagamento a produtor só podem ser estornados
    pela tela do pagamento (permitir_vinculado=True), para os dois ficarem iguais.
    """
    # Recarrega travando a linha: evita dois estornos ao mesmo tempo.
    lancamento = Lancamento.objects.select_for_update().get(pk=lancamento.pk)
    if lancamento.estornado:
        raise ValidationError("Este lançamento já foi estornado.")
    if not permitir_vinculado and hasattr(lancamento, "pagamento_produtor"):
        raise ValidationError(
            "Este lançamento veio de um pagamento a produtor. Estorne pelo menu Leite > Pagamentos."
        )
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo do estorno.")
    lancamento.estornado = True
    lancamento.estornado_em = timezone.now()
    lancamento.estornado_por = usuario
    lancamento.motivo_estorno = motivo[:200]
    lancamento.save(update_fields=["estornado", "estornado_em", "estornado_por", "motivo_estorno"])
    logger.info("Lançamento %s estornado por %s: %s", lancamento.pk, usuario, motivo)
    return lancamento


def lancamentos_validos():
    """Lançamentos que contam nos totais (os estornados ficam de fora)."""
    return Lancamento.objects.filter(estornado=False)


def totais(consulta):
    """Soma entradas e saídas de uma consulta e devolve também o saldo."""
    entradas = consulta.filter(tipo=TipoLancamento.ENTRADA).aggregate(t=Sum("valor"))["t"] or Decimal("0")
    saidas = consulta.filter(tipo=TipoLancamento.SAIDA).aggregate(t=Sum("valor"))["t"] or Decimal("0")
    return {"entradas": entradas, "saidas": saidas, "saldo": entradas - saidas}


def totais_periodo(inicio, fim):
    return totais(lancamentos_validos().filter(data__gte=inicio, data__lte=fim))


def somas_por_categoria(consulta, tipo):
    """Lista [(categoria, total)] do maior para o menor, só de um tipo."""
    linhas = (
        consulta.filter(tipo=tipo)
        .values("categoria__nome")
        .annotate(total=Sum("valor"))
        .order_by("-total")
    )
    return [(linha["categoria__nome"], linha["total"]) for linha in linhas]


def serie_mensal(meses=6):
    """Entradas e saídas dos últimos N meses (para o gráfico do dashboard)."""
    lista = ultimos_meses(meses)
    dados = OrderedDict(((ano, mes), {"entradas": Decimal("0"), "saidas": Decimal("0")}) for ano, mes in lista)
    ano0, mes0 = lista[0]
    linhas = (
        lancamentos_validos()
        .filter(data__gte=f"{ano0:04d}-{mes0:02d}-01")
        .values("data__year", "data__month", "tipo")
        .annotate(total=Sum("valor"))
    )
    for linha in linhas:
        chave = (linha["data__year"], linha["data__month"])
        if chave in dados:
            campo = "entradas" if linha["tipo"] == TipoLancamento.ENTRADA else "saidas"
            dados[chave][campo] = linha["total"]
    return {
        "rotulos": [f"{NOMES_MESES[m - 1][:3]}/{str(a)[2:]}" for a, m in dados],
        "entradas": [float(v["entradas"]) for v in dados.values()],
        "saidas": [float(v["saidas"]) for v in dados.values()],
    }
