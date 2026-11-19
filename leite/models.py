"""
leite/models.py
===============
Tabelas do leite:

- Produtor: quem fornece o leite (no Streamlit era só um nome solto na tabela "leite").
- Coleta: quantos litros de um produtor num dia (um registro por produtor por dia).
  * litros = 0 significa FALTA (dia sem entrega), igual ao sistema antigo.
  * preco_litro é copiado do cadastro do produtor no momento do lançamento.
- PagamentoProdutor: dinheiro pago ao produtor. Com isso o sistema sabe o SALDO
  (leite recebido - pagamentos), coisa que o Streamlit não controlava.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from core.escolhas import FormaPagamento
from core.utils import dinheiro


class Produtor(models.Model):
    nome = models.CharField("Nome", max_length=120)
    apelido_propriedade = models.CharField("Propriedade / sítio", max_length=120, blank=True)
    cpf = models.CharField("CPF", max_length=14, blank=True)
    telefone = models.CharField("Telefone (WhatsApp)", max_length=20, blank=True)
    chave_pix = models.CharField("Chave Pix", max_length=120, blank=True)
    preco_litro = models.DecimalField(
        "Preço do litro (R$)", max_digits=8, decimal_places=2, default=Decimal("2.00"),
        help_text="Usado em todo lançamento novo deste produtor.",
    )
    ativo = models.BooleanField("Ativo", default=True, help_text="Produtores inativos não aparecem na coleta.")
    observacao = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "produtor"
        verbose_name_plural = "produtores"
        ordering = ["nome"]
        constraints = [
            # Não deixa cadastrar "João" e "joão" como produtores diferentes.
            models.UniqueConstraint(Lower("nome"), name="produtor_nome_unico"),
            models.CheckConstraint(condition=Q(preco_litro__gte=0), name="produtor_preco_nao_negativo"),
        ]

    def __str__(self):
        return self.nome


class FormaColeta(models.TextChoices):
    COLETADO = "COLETADO", "Coletado na propriedade"
    ENTREGUE = "ENTREGUE", "Entregue pelo produtor"
    ESCRITORIO = "ESCRITORIO", "Lançado no escritório"


class Coleta(models.Model):
    produtor = models.ForeignKey(Produtor, on_delete=models.PROTECT, related_name="coletas")
    data = models.DateField("Data")
    litros = models.DecimalField("Litros", max_digits=8, decimal_places=1)
    preco_litro = models.DecimalField("Preço do litro (R$)", max_digits=8, decimal_places=2)
    forma = models.CharField("Forma", max_length=10, choices=FormaColeta.choices, default=FormaColeta.ESCRITORIO)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Lançado por",
    )
    criado_em = models.DateTimeField("Lançado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Alterado em", auto_now=True)
    # Código único gerado no CELULAR quando o leite é lançado offline.
    # Se a internet cair no meio do envio e o celular mandar de novo, o servidor
    # reconhece o código e não grava o mesmo leite duas vezes.
    codigo_offline = models.UUIDField("Código do celular", null=True, blank=True, unique=True, editable=False)

    class Meta:
        verbose_name = "coleta de leite"
        verbose_name_plural = "coletas de leite"
        ordering = ["data", "produtor__nome"]
        permissions = [
            ("registrar_coleta_diaria", "Pode usar a página de coleta diária"),
            ("alterar_preco_massa", "Pode alterar o preço do leite em massa"),
            ("emitir_recibo", "Pode emitir recibo do produtor"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["produtor", "data"], name="coleta_um_por_dia"),
            models.CheckConstraint(condition=Q(litros__gte=0), name="coleta_litros_nao_negativo"),
            models.CheckConstraint(condition=Q(preco_litro__gte=0), name="coleta_preco_nao_negativo"),
        ]
        indexes = [models.Index(fields=["data"])]

    def __str__(self):
        return f"{self.produtor} - {self.data:%d/%m/%Y} - {self.litros} L"

    @property
    def falta(self):
        """True quando o dia foi marcado como falta (0 litros)."""
        return self.litros == 0

    @property
    def valor_total(self):
        """Litros x preço, arredondado em centavos."""
        return dinheiro(self.litros * self.preco_litro)


class PagamentoProdutor(models.Model):
    produtor = models.ForeignKey(Produtor, on_delete=models.PROTECT, related_name="pagamentos")
    data = models.DateField("Data do pagamento")
    valor = models.DecimalField("Valor pago (R$)", max_digits=12, decimal_places=2)
    forma_pagamento = models.CharField("Forma de pagamento", max_length=15, choices=FormaPagamento.choices)
    valor_dinheiro = models.DecimalField("Parte em dinheiro", max_digits=12, decimal_places=2, default=0)
    valor_pix = models.DecimalField("Parte em Pix", max_digits=12, decimal_places=2, default=0)
    periodo_inicio = models.DateField("Referente ao período de", null=True, blank=True)
    periodo_fim = models.DateField("até", null=True, blank=True)
    observacao = models.CharField("Observação", max_length=200, blank=True)
    # Saída gerada automaticamente no caixa (financeiro).
    lancamento = models.OneToOneField(
        "financeiro.Lancamento", on_delete=models.PROTECT, null=True, blank=True, related_name="pagamento_produtor"
    )
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    criado_em = models.DateTimeField(auto_now_add=True)

    estornado = models.BooleanField("Estornado", default=False)
    estornado_em = models.DateTimeField(null=True, blank=True)
    motivo_estorno = models.CharField("Motivo do estorno", max_length=200, blank=True)

    class Meta:
        verbose_name = "pagamento a produtor"
        verbose_name_plural = "pagamentos a produtores"
        ordering = ["-data", "-id"]
        default_permissions = ("view", "add")
        permissions = [("estornar_pagamento", "Pode estornar pagamento a produtor")]
        constraints = [
            models.CheckConstraint(condition=Q(valor__gt=0), name="pagamento_valor_positivo"),
        ]

    def __str__(self):
        return f"{self.produtor} - R$ {self.valor} em {self.data:%d/%m/%Y}"
