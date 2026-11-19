"""
core/models.py
==============
Dados do próprio laticínio (nome, documento, telefone, endereço, chave Pix).
É um "singleton": existe um registro só, sempre com id=1.
Esses dados aparecem no cabeçalho do recibo e nas mensagens de WhatsApp.
"""

from django.db import models


class DadosEmpresa(models.Model):
    nome = models.CharField("Nome do laticínio", max_length=120, default="Laticínio Braga")
    documento = models.CharField("CPF/CNPJ", max_length=20, blank=True)
    telefone = models.CharField("Telefone", max_length=20, blank=True)
    endereco = models.CharField("Endereço", max_length=200, blank=True)
    cidade = models.CharField("Cidade/UF", max_length=80, blank=True)
    responsavel = models.CharField("Responsável (assina os recibos)", max_length=120, blank=True)

    class Meta:
        verbose_name = "dados do laticínio"
        verbose_name_plural = "dados do laticínio"
        default_permissions = ("view", "change")

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        # Força sempre o id=1 para nunca existir mais de um registro.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obter(cls):
        """Devolve o registro único (cria na primeira vez)."""
        objeto, _ = cls.objects.get_or_create(pk=1)
        return objeto
