"""
contas/forms.py
===============
Formulários de login, usuários e níveis de acesso.
"""

import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import Group, User

from core.utils import estilizar_campos


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Usuário"
        self.fields["username"].widget.attrs.update({"autofocus": True, "autocomplete": "username"})
        estilizar_campos(self)


class TrocarSenhaForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)


class UsuarioCriarForm(forms.Form):
    username = forms.CharField(label="Usuário (login)", max_length=30)
    nome = forms.CharField(label="Nome", max_length=150)
    email = forms.EmailField(label="E-mail", required=False)
    nivel = forms.ModelChoiceField(label="Nível de acesso", queryset=Group.objects.all(), required=False,
                                   empty_label="(nenhum)")
    administrador = forms.BooleanField(label="Administrador (acesso total, inclusive usuários)", required=False)
    exigir_troca = forms.BooleanField(label="Exigir troca de senha no primeiro acesso", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if not re.fullmatch(r"[a-z0-9_.-]{3,30}", username):
            raise forms.ValidationError("Use de 3 a 30 letras minúsculas, números, ponto, hífen ou _ (sem espaços).")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Este usuário já existe.")
        return username

    def clean(self):
        dados = super().clean()
        if not dados.get("nivel") and not dados.get("administrador"):
            raise forms.ValidationError("Escolha um nível de acesso ou marque Administrador.")
        return dados


class UsuarioEditarForm(forms.Form):
    nome = forms.CharField(label="Nome", max_length=150)
    email = forms.EmailField(label="E-mail", required=False)
    nivel = forms.ModelChoiceField(label="Nível de acesso", queryset=Group.objects.all(), required=False,
                                   empty_label="(nenhum)")
    administrador = forms.BooleanField(label="Administrador", required=False)
    ativo = forms.BooleanField(label="Ativo (pode entrar no sistema)", required=False)
    exigir_troca = forms.BooleanField(label="Exigir troca de senha no próximo acesso", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)


class NivelForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name"]
        labels = {"name": "Nome do nível"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)
