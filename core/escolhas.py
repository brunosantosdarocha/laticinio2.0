"""
core/escolhas.py
================
Listas de opções (choices) usadas em mais de um app.
Ficam num lugar só para não repetir texto e manter tudo igual no sistema todo.
"""

from django.db import models


class FormaPagamento(models.TextChoices):
    """Formas de pagamento aceitas em pagamentos a produtores e lançamentos do caixa."""

    DINHEIRO = "DINHEIRO", "Dinheiro"
    PIX = "PIX", "Pix"
    MISTO = "MISTO", "Misto (dinheiro + Pix)"
    TRANSFERENCIA = "TRANSFERENCIA", "Transferência bancária"
    DEBITO = "DEBITO", "Cartão de débito"
    CREDITO = "CREDITO", "Cartão de crédito"
    BOLETO = "BOLETO", "Boleto"
    CHEQUE = "CHEQUE", "Cheque"


NOMES_MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

NOMES_DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
