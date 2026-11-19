"""
backup/models.py
================
- ConfiguracaoBackup: e-mail de destino, horário do backup automático e dados do SMTP.
  A senha do e-mail fica CRIPTOGRAFADA (Fernet) — nunca em texto puro no banco.
- RegistroBackup: histórico de cada backup feito (somente leitura).
"""

from django.conf import settings
from django.db import models

from . import cripto


class ConfiguracaoBackup(models.Model):
    ativo = models.BooleanField("Backup automático ligado", default=False)
    email_destino = models.EmailField("Enviar para o e-mail", blank=True)
    horario = models.TimeField("Horário do backup diário", default="22:00")
    smtp_host = models.CharField("Servidor SMTP", max_length=120, default="smtp.gmail.com")
    smtp_porta = models.PositiveIntegerField("Porta", default=587)
    smtp_usuario = models.CharField("Usuário do e-mail (remetente)", max_length=120, blank=True)
    smtp_senha_cifrada = models.TextField(blank=True, editable=False)
    smtp_tls = models.BooleanField("Usar TLS", default=True)
    ultimo_backup_auto = models.DateTimeField("Último backup automático", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "configuração de backup"
        default_permissions = ()
        permissions = [("gerenciar_backup", "Pode configurar, enviar e baixar backups")]

    def __str__(self):
        return "Configuração de backup"

    def save(self, *args, **kwargs):
        self.pk = 1  # registro único
        super().save(*args, **kwargs)

    @classmethod
    def obter(cls):
        objeto, _ = cls.objects.get_or_create(pk=1)
        return objeto

    def definir_senha(self, senha):
        self.smtp_senha_cifrada = cripto.cifrar(senha) if senha else ""

    def obter_senha(self):
        return cripto.decifrar(self.smtp_senha_cifrada) if self.smtp_senha_cifrada else ""

    @property
    def smtp_configurado(self):
        return bool(self.smtp_host and self.smtp_usuario and self.smtp_senha_cifrada)


class RegistroBackup(models.Model):
    class Origem(models.TextChoices):
        MANUAL = "MANUAL", "Enviado pela tela"
        AUTOMATICO = "AUTO", "Automático (agendado)"
        DOWNLOAD = "DOWNLOAD", "Baixado pela tela"
        COMANDO = "COMANDO", "Comando no terminal"

    criado_em = models.DateTimeField("Data", auto_now_add=True)
    arquivo = models.CharField("Arquivo", max_length=200)
    tamanho = models.PositiveIntegerField("Tamanho (bytes)", default=0)
    origem = models.CharField("Origem", max_length=10, choices=Origem.choices)
    enviado_para = models.CharField("Enviado para", max_length=200, blank=True)
    sucesso = models.BooleanField("Sucesso", default=True)
    mensagem = models.TextField("Mensagem", blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        verbose_name = "registro de backup"
        verbose_name_plural = "registros de backup"
        ordering = ["-criado_em"]
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.arquivo} ({self.criado_em:%d/%m/%Y %H:%M})"
