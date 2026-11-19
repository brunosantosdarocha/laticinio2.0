"""
Comando: python manage.py restaurar_backup arquivo.zip

Troca o banco atual pelo banco do backup.
ANTES de trocar, guarda uma cópia do banco atual em backups/antes_da_restauracao_<data>.sqlite3.
Use com o sistema DESLIGADO.
"""

import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = "Restaura o banco de dados a partir de um backup .zip."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="Caminho do arquivo .zip do backup")
        parser.add_argument("--sim", action="store_true", help="Não pergunta confirmação")

    def handle(self, *args, **options):
        arquivo = Path(options["arquivo"])
        if not arquivo.exists():
            # Também procura dentro da pasta backups/
            arquivo = Path(settings.PASTA_BACKUPS) / options["arquivo"]
        if not arquivo.exists() or not zipfile.is_zipfile(arquivo):
            raise CommandError("Arquivo de backup não encontrado ou não é um .zip válido.")

        with zipfile.ZipFile(arquivo) as zip_:
            if "banco.sqlite3" not in zip_.namelist():
                raise CommandError("Este .zip não tem o arquivo banco.sqlite3. Não parece um backup do sistema.")
            if not options["sim"]:
                resposta = input("O banco atual será SUBSTITUÍDO pelo backup. Continuar? [s/N] ")
                if resposta.strip().lower() not in ("s", "sim"):
                    self.stdout.write("Cancelado.")
                    return
            banco_atual = Path(settings.DATABASES["default"]["NAME"])
            connection.close()
            pasta = Path(settings.PASTA_BACKUPS)
            pasta.mkdir(exist_ok=True)
            if banco_atual.exists():
                copia = pasta / f"antes_da_restauracao_{timezone.localtime():%Y-%m-%d_%H%M%S}.sqlite3"
                shutil.copy2(banco_atual, copia)
                self.stdout.write(f"Cópia do banco atual guardada em {copia}")
            with tempfile.TemporaryDirectory() as temporaria:
                extraido = Path(zip_.extract("banco.sqlite3", temporaria))
                # Confere se o arquivo é mesmo um banco SQLite íntegro antes de usar.
                with sqlite3.connect(extraido) as teste:
                    if teste.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise CommandError("O banco dentro do backup está corrompido.")
                teste.close()
                shutil.copy2(extraido, banco_atual)
        self.stdout.write(self.style.SUCCESS("Backup restaurado! Rode 'python iniciar.py' para ligar o sistema."))
