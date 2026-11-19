"""core/forms.py - formulário dos dados do laticínio."""

from django import forms

from .models import DadosEmpresa
from .utils import estilizar_campos
from .validadores import formatar_cpf_ou_cnpj, formatar_telefone, validar_cpf_ou_cnpj, validar_telefone


class DadosEmpresaForm(forms.ModelForm):
    class Meta:
        model = DadosEmpresa
        fields = ["nome", "documento", "telefone", "endereco", "cidade", "responsavel"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)

    def clean_documento(self):
        valor = self.cleaned_data["documento"].strip()
        validar_cpf_ou_cnpj(valor)
        return formatar_cpf_ou_cnpj(valor) if valor else ""

    def clean_telefone(self):
        valor = self.cleaned_data["telefone"].strip()
        validar_telefone(valor)
        return formatar_telefone(valor) if valor else ""
