"""
Comando: python manage.py configurar_grupos [--redefinir]

Cria os níveis de acesso padrão (Gerente, Escritório, Coletor) se ainda não existirem.
Com --redefinir, volta as permissões desses níveis para o padrão de fábrica.
"""

from django.core.management.base import BaseCommand

from contas.servicos import configurar_grupos_padrao


class Command(BaseCommand):
    help = "Cria os níveis de acesso padrão."

    def add_arguments(self, parser):
        parser.add_argument("--redefinir", action="store_true", help="Volta as permissões dos níveis padrão ao original.")

    def handle(self, *args, **options):
        alterados = configurar_grupos_padrao(redefinir=options["redefinir"])
        if alterados:
            self.stdout.write(self.style.SUCCESS("Níveis configurados: " + ", ".join(alterados)))
        else:
            self.stdout.write("Níveis de acesso já existem. Nada a fazer.")
