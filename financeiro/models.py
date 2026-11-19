"""
financeiro/models.py
====================
Caixa do laticínio: entradas e saídas de dinheiro.

No Streamlit havia uma tabela com 20 colunas fixas (saida1..saida10, entrada1..entrada10).
Agora cada movimento é UMA linha com tipo + categoria. Vantagens:
- dá para criar/renomear categorias pela tela, sem mexer no código;
- os relatórios ficam simples (somar por categoria, por mês...);
- erro não se apaga: faz-se ESTORNO (o registro fica no histórico, mas sai dos totais).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.escolhas import FormaPagamento


class TipoLancamento(models.TextChoices):
    ENTRADA = "ENTRADA", "Entrada"
    SAIDA = "SAIDA", "Saída"


class Categoria(models.Model):
    """Tipo de entrada ou de saída (ex.: 'Queijos', 'Combustível / Diesel')."""

    nome = models.CharField("Nome", max_length=80)
    tipo = models.CharField("Tipo", max_length=7, choices=TipoLancamento.choices)
    ativa = models.BooleanField("Ativa", default=True)
    # Categorias do sistema (ex.: "Pagamento a produtores") não podem ser desativadas.
    sistema = models.BooleanField("Categoria do sistema", default=False, editable=False)

    class Meta:
        verbose_name = "categoria"
        ordering = ["tipo", "nome"]
        default_permissions = ("view", "add", "change")
        constraints = [
            models.UniqueConstraint(fields=["nome", "tipo"], name="categoria_nome_tipo_unico"),
        ]

    def __str__(self):
        return self.nome


class Lancamento(models.Model):
    """Um movimento do caixa. Nunca é apagado: erros são corrigidos com estorno."""

    tipo = models.CharField("Tipo", max_length=7, choices=TipoLancamento.choices)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, verbose_name="Categoria")
    valor = models.DecimalField("Valor (R$)", max_digits=12, decimal_places=2)
    data = models.DateField("Data")
    descricao = models.CharField("Observação / descrição", max_length=200, blank=True)
    forma_pagamento = models.CharField(
        "Forma de pagamento", max_length=15, choices=FormaPagamento.choices, blank=True
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
        verbose_name="Lançado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    # Estorno (correção de erro)
    estornado = models.BooleanField("Estornado", default=False)
    estornado_em = models.DateTimeField("Estornado em", null=True, blank=True)
    estornado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    motivo_estorno = models.CharField("Motivo do estorno", max_length=200, blank=True)

    class Meta:
        verbose_name = "lançamento"
        ordering = ["-data", "-id"]
        default_permissions = ("view", "add")
        permissions = [("estornar_lancamento", "Pode estornar lançamentos do caixa")]
        constraints = [
            models.CheckConstraint(condition=Q(valor__gt=0), name="lancamento_valor_positivo"),
        ]
        indexes = [models.Index(fields=["data", "tipo"])]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.categoria} R$ {self.valor} em {self.data:%d/%m/%Y}"
