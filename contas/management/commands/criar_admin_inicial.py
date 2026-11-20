"""
Comando: python manage.py criar_admin_inicial [--senha-aleatoria]

Cria o usuário admin / admin123 SOMENTE se ainda não existir nenhum administrador.
Com --senha-aleatoria (use em servidor na internet, ex.: PythonAnywhere), a senha
é gerada na hora e mostrada uma única vez.
O admin NÃO é obrigado a trocar a senha no primeiro acesso.
"""

import secrets

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from contas.models import Perfil


class Command(BaseCommand):
    help = "Cria o administrador inicial (admin/admin123) se não existir nenhum."

    def add_arguments(self, parser):
        parser.add_argument(
            "--senha-aleatoria", action="store_true",
            help="Gera uma senha forte em vez de admin123 (recomendado na internet).",
        )

    def handle(self, *args, **options):
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("Administrador já existe. Nada a fazer.")
            return
        senha = secrets.token_urlsafe(12) if options["senha_aleatoria"] else "admin123"
        usuario = User.objects.create_superuser("admin", "", senha, first_name="Administrador")
        # O admin NÃO é obrigado a trocar a senha no primeiro acesso.
        Perfil.objects.update_or_create(usuario=usuario, defaults={"deve_trocar_senha": False})
        self.stdout.write(self.style.SUCCESS(
            f"Administrador criado: usuário 'admin' e senha '{senha}'."
        ))
        if options["senha_aleatoria"]:
            self.stdout.write(self.style.WARNING("ANOTE ESTA SENHA AGORA: ela não será mostrada de novo."))
