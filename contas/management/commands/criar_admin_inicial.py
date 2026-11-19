"""
Comando: python manage.py criar_admin_inicial

Cria o usuário admin / admin123 SOMENTE se ainda não existir nenhum administrador.
O admin NÃO é obrigado a trocar a senha no primeiro acesso.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from contas.models import Perfil


class Command(BaseCommand):
    help = "Cria o administrador inicial (admin/admin123) se não existir nenhum."

    def handle(self, *args, **options):
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("Administrador já existe. Nada a fazer.")
            return
        usuario = User.objects.create_superuser("admin", "", "admin123", first_name="Administrador")
        # O admin NÃO é obrigado a trocar a senha no primeiro acesso.
        Perfil.objects.update_or_create(usuario=usuario, defaults={"deve_trocar_senha": False})
        self.stdout.write(self.style.SUCCESS(
            "Administrador criado: usuário 'admin' e senha 'admin123'."
        ))
