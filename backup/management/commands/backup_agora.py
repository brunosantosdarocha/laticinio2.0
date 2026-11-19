"""
Comando: python manage.py backup_agora [--enviar]

Cria um backup na pasta backups/ (e envia por e-mail com --enviar).
"""

from django.core.management.base import BaseCommand, CommandError

from backup.models import RegistroBackup
from backup.servicos import fazer_backup


class Command(BaseCommand):
    help = "Cria um backup agora."

    def add_arguments(self, parser):
        parser.add_argument("--enviar", action="store_true", help="Envia o backup para o e-mail configurado.")

    def handle(self, *args, **options):
        registro = fazer_backup(origem=RegistroBackup.Origem.COMANDO, enviar=options["enviar"])
        if not registro.sucesso:
            raise CommandError(registro.mensagem)
        self.stdout.write(self.style.SUCCESS(f"{registro.mensagem} Arquivo: backups/{registro.arquivo}"))
