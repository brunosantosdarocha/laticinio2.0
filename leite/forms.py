"""
leite/forms.py
==============
Formulários das telas do leite. Sempre com a lista de campos explícita (nunca "__all__"),
para nenhum campo "escondido" ser alterado por quem envia o formulário.
"""

import datetime
from decimal import Decimal

from django import forms
from django.utils import timezone

from core.escolhas import FormaPagamento
from core.utils import estilizar_campos, primeiro_dia_mes, ultimo_dia_mes
from core.validadores import formatar_cpf, formatar_telefone, validar_cpf, validar_telefone

from .models import Coleta, FormaColeta, PagamentoProdutor, Produtor


class ProdutorForm(forms.ModelForm):
    class Meta:
        model = Produtor
        fields = ["nome", "apelido_propriedade", "cpf", "telefone", "chave_pix", "preco_litro", "ativo", "observacao"]
        widgets = {"observacao": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preco_litro"].widget.attrs.update({"step": "0.01", "min": "0"})
        estilizar_campos(self)

    def clean_nome(self):
        """Tira espaços sobrando e impede nome repetido (sem diferenciar maiúsculas)."""
        nome = " ".join(self.cleaned_data["nome"].split())
        repetido = Produtor.objects.filter(nome__iexact=nome).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Já existe um produtor com este nome.")
        return nome

    def clean_cpf(self):
        cpf = self.cleaned_data["cpf"].strip()
        validar_cpf(cpf)
        return formatar_cpf(cpf) if cpf else ""

    def clean_telefone(self):
        telefone = self.cleaned_data["telefone"].strip()
        validar_telefone(telefone)
        return formatar_telefone(telefone) if telefone else ""

    def clean_preco_litro(self):
        preco = self.cleaned_data["preco_litro"]
        if preco < 0:
            raise forms.ValidationError("O preço não pode ser negativo.")
        return preco


class ColetaDiariaForm(forms.Form):
    """Formulário da página do coletor: produtor, coletado/entregue e litros."""

    produtor = forms.ModelChoiceField(
        queryset=Produtor.objects.filter(ativo=True), label="Produtor", empty_label="Escolha o produtor..."
    )
    forma = forms.ChoiceField(
        label="O leite foi...",
        choices=[(FormaColeta.COLETADO, "Coletado"), (FormaColeta.ENTREGUE, "Entregue")],
        widget=forms.RadioSelect,
        initial=FormaColeta.COLETADO,
    )
    litros = forms.DecimalField(
        label="Litros", min_value=Decimal("0.1"), max_value=Decimal("99999.9"), decimal_places=1, max_digits=6,
        widget=forms.NumberInput(attrs={"step": "0.1", "inputmode": "decimal", "placeholder": "0", "autocomplete": "off"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)
        self.fields["produtor"].widget.attrs["class"] += " form-select-lg"
        self.fields["litros"].widget.attrs["class"] += " form-control-lg text-center fs-2 fw-bold"


class ColetaEditarForm(forms.ModelForm):
    """Correção de um lançamento (escritório)."""

    class Meta:
        model = Coleta
        fields = ["litros", "preco_litro", "forma"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["litros"].widget.attrs.update({"step": "0.1", "min": "0"})
        self.fields["preco_litro"].widget.attrs.update({"step": "0.01", "min": "0"})
        self.fields["litros"].help_text = "Use 0 para marcar o dia como falta."
        estilizar_campos(self)


class PrecoMassaForm(forms.Form):
    todos_produtores = forms.BooleanField(label="Aplicar para TODOS os produtores", required=False)
    filtrar_preco = forms.BooleanField(
        label="Alterar somente os registros que estão com um preço específico", required=False, initial=True
    )
    preco_atual = forms.DecimalField(label="Preço atual a substituir (R$)", required=False, min_value=0, decimal_places=2)
    novo_preco = forms.DecimalField(label="Novo preço por litro (R$)", min_value=0, decimal_places=2)
    inicio = forms.DateField(label="A partir de", widget=forms.DateInput)
    fim = forms.DateField(label="Até", widget=forms.DateInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ("preco_atual", "novo_preco"):
            self.fields[nome].widget.attrs.update({"step": "0.01"})
        estilizar_campos(self)

    def clean(self):
        dados = super().clean()
        if dados.get("inicio") and dados.get("fim") and dados["inicio"] > dados["fim"]:
            raise forms.ValidationError("A data de início não pode ser maior que a data final.")
        if dados.get("filtrar_preco") and dados.get("preco_atual") is None:
            self.add_error("preco_atual", "Informe o preço atual ou desmarque o filtro.")
        return dados


class PeriodoForm(forms.Form):
    """Escolha de período (recibo, extrato do produtor)."""

    inicio = forms.DateField(label="Data de início", widget=forms.DateInput)
    fim = forms.DateField(label="Data final", widget=forms.DateInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)

    def clean(self):
        dados = super().clean()
        if dados.get("inicio") and dados.get("fim"):
            if dados["inicio"] > dados["fim"]:
                raise forms.ValidationError("A data de início não pode ser maior do que a data final.")
            if (dados["fim"] - dados["inicio"]).days > 366:
                raise forms.ValidationError("Escolha um período de no máximo 1 ano.")
        return dados

    @staticmethod
    def periodo_padrao():
        hoje = timezone.localdate()
        return primeiro_dia_mes(hoje), ultimo_dia_mes(hoje)


class PagamentoForm(forms.ModelForm):
    """Pagamento ao produtor. A forma "misto" exige dinheiro + Pix = valor."""

    class Meta:
        model = PagamentoProdutor
        fields = ["data", "valor", "forma_pagamento", "valor_dinheiro", "valor_pix",
                  "periodo_inicio", "periodo_fim", "observacao"]
        widgets = {
            "data": forms.DateInput, "periodo_inicio": forms.DateInput, "periodo_fim": forms.DateInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["forma_pagamento"].choices = [
            (v, r) for v, r in FormaPagamento.choices
            if v in (FormaPagamento.DINHEIRO, FormaPagamento.PIX, FormaPagamento.MISTO,
                     FormaPagamento.TRANSFERENCIA, FormaPagamento.CHEQUE)
        ]
        self.fields["valor_dinheiro"].required = False
        self.fields["valor_pix"].required = False
        for nome in ("valor", "valor_dinheiro", "valor_pix"):
            self.fields[nome].widget.attrs.update({"step": "0.01", "min": "0"})
        # Marcações usadas pelo JavaScript do pagamento misto.
        self.fields["valor"].widget.attrs["data-pg-total"] = "1"
        self.fields["forma_pagamento"].widget.attrs["data-pg-forma"] = "1"
        self.fields["valor_dinheiro"].widget.attrs["data-pg-dinheiro"] = "1"
        self.fields["valor_pix"].widget.attrs["data-pg-pix"] = "1"
        estilizar_campos(self)

    def clean(self):
        dados = super().clean()
        valor = dados.get("valor")
        if valor is not None and valor <= 0:
            self.add_error("valor", "Informe um valor maior que zero.")
        if dados.get("forma_pagamento") == FormaPagamento.MISTO and valor:
            dinheiro_ = dados.get("valor_dinheiro") or 0
            pix = dados.get("valor_pix") or 0
            if dinheiro_ <= 0 or pix <= 0 or dinheiro_ + pix != valor:
                raise forms.ValidationError("No pagamento misto, dinheiro + Pix precisa fechar exatamente o valor pago.")
        inicio, fim = dados.get("periodo_inicio"), dados.get("periodo_fim")
        if inicio and fim and inicio > fim:
            self.add_error("periodo_fim", "O fim do período não pode ser antes do início.")
        data = dados.get("data")
        if data and data > timezone.localdate() + datetime.timedelta(days=1):
            self.add_error("data", "A data do pagamento não pode estar no futuro.")
        return dados


class EstornoForm(forms.Form):
    motivo = forms.CharField(label="Motivo do estorno", max_length=200)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)
