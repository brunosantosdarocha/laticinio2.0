"""
contas/models.py
================
Perfil: informação extra de cada usuário do Django.
Por enquanto guarda só se a pessoa precisa trocar a senha no próximo acesso
(só quando o administrador marca "Exigir troca de senha").
"""

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Perfil(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    deve_trocar_senha = models.BooleanField("Deve trocar a senha no próximo acesso", default=False)

    class Meta:
        verbose_name = "perfil"
        verbose_name_plural = "perfis"

    def __str__(self):
        return f"Perfil de {self.usuario}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def criar_perfil(sender, instance, created, **kwargs):
    """Todo usuário novo ganha um Perfil automaticamente."""
    if created:
        Perfil.objects.get_or_create(usuario=instance)
