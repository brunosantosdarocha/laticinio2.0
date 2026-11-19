"""backup/forms.py - formulário da configuração de backup."""

from django import forms

from core.utils import estilizar_campos

from .models import ConfiguracaoBackup


class ConfiguracaoBackupForm(forms.ModelForm):
    # A senha nunca é mostrada de volta na tela. Deixe em branco para manter a atual.
    smtp_senha = forms.CharField(
        label="Senha do e-mail (senha de app)", required=False, widget=forms.PasswordInput(render_value=False),
        help_text="Deixe em branco para manter a senha já salva.",
    )

    class Meta:
        model = ConfiguracaoBackup
        fields = ["ativo", "email_destino", "horario", "smtp_host", "smtp_porta", "smtp_usuario", "smtp_tls"]
        widgets = {"horario": forms.TimeInput}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)

    def clean(self):
        dados = super().clean()
        if dados.get("ativo") and not dados.get("email_destino"):
            self.add_error("email_destino", "Informe o e-mail para ligar o backup automático.")
        return dados

    def save(self, commit=True):
        config = super().save(commit=False)
        senha = self.cleaned_data.get("smtp_senha")
        if senha:
            config.definir_senha(senha.replace(" ", ""))  # senha de app do Gmail vem com espaços
        if commit:
            config.save()
        return config
