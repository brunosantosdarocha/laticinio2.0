"""
financeiro/forms.py
===================
Formulários do caixa: novo lançamento, filtro do extrato e categorias.
"""

from django import forms

from core.utils import estilizar_campos

from .models import Categoria, Lancamento, TipoLancamento


class LancamentoForm(forms.ModelForm):
    """Nova entrada ou saída. O tipo vem da URL (a view informa), não do formulário."""

    class Meta:
        model = Lancamento
        fields = ["data", "categoria", "valor", "forma_pagamento", "descricao"]
        widgets = {"data": forms.DateInput}

    def __init__(self, *args, tipo, **kwargs):
        super().__init__(*args, **kwargs)
        self.tipo = tipo
        # Só aparecem as categorias ativas do tipo certo.
        self.fields["categoria"].queryset = Categoria.objects.filter(tipo=tipo, ativa=True).exclude(sistema=True)
        self.fields["valor"].widget.attrs.update({"step": "0.01", "min": "0.01"})
        estilizar_campos(self)

    def clean_valor(self):
        valor = self.cleaned_data["valor"]
        if valor <= 0:
            raise forms.ValidationError("Insira um valor maior que zero.")
        return valor


class FiltroExtratoForm(forms.Form):
    inicio = forms.DateField(label="De", required=False, widget=forms.DateInput)
    fim = forms.DateField(label="Até", required=False, widget=forms.DateInput)
    tipo = forms.ChoiceField(label="Tipo", required=False, choices=[("", "Todos")] + list(TipoLancamento.choices))
    categoria = forms.ModelChoiceField(label="Categoria", required=False, queryset=Categoria.objects.all(),
                                       empty_label="Todas")
    q = forms.CharField(label="Buscar na descrição", required=False, max_length=100)
    estornados = forms.BooleanField(label="Mostrar estornados", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nome", "tipo", "ativa"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Mudar o tipo de uma categoria já usada bagunçaria os relatórios.
            self.fields["tipo"].disabled = True
        estilizar_campos(self)

    def clean_nome(self):
        return " ".join(self.cleaned_data["nome"].split())

    def clean(self):
        dados = super().clean()
        nome, tipo = dados.get("nome"), dados.get("tipo") or self.instance.tipo
        if nome and tipo:
            repetida = Categoria.objects.filter(nome__iexact=nome, tipo=tipo).exclude(pk=self.instance.pk)
            if repetida.exists():
                self.add_error("nome", "Já existe uma categoria com este nome.")
        return dados


class EstornoForm(forms.Form):
    motivo = forms.CharField(label="Motivo do estorno", max_length=200)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)
