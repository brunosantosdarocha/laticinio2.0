"""
Comando: python manage.py popular_demo [--usuarios]

Cria dados de EXEMPLO para testar o sistema: produtores, 90 dias de leite,
pagamentos e lançamentos do caixa. Com --usuarios cria também:
  gerente / Gerente@2026   escritorio / Escritorio@2026   coletor / Coletor@2026
Não use em um banco com dados reais!
"""

import datetime
import random
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.utils import timezone

from contas.models import Perfil
from contas.servicos import configurar_grupos_padrao
from core.models import DadosEmpresa
from financeiro.models import Categoria, Lancamento, TipoLancamento
from leite import servicos as leite_servicos
from leite.models import Coleta, FormaColeta, Produtor

PRODUTORES = [
    ("José Carlos da Silva", "Sítio Boa Vista", "2.30", 120),
    ("Maria Aparecida Souza", "Fazenda Santa Rita", "2.40", 210),
    ("Antônio Pereira", "Sítio Cachoeira", "2.20", 65),
    ("Flávio Rocha", "Fazenda Pedra Bonita", "2.35", 150),
    ("Sebastião Gomes", "Sítio Recanto", "2.20", 45),
    ("Luzia Fernandes", "Chácara Primavera", "2.25", 80),
    ("Geraldo Moreira", "Sítio Água Limpa", "2.30", 95),
]


class Command(BaseCommand):
    help = "Cria dados de exemplo (demonstração)."

    def add_arguments(self, parser):
        parser.add_argument("--usuarios", action="store_true", help="Cria também usuários de exemplo.")

    def handle(self, *args, **options):
        random.seed(42)
        hoje = timezone.localdate()
        empresa = DadosEmpresa.obter()
        empresa.nome = "Laticínio Braga"
        empresa.cidade = "Vitória/ES"
        empresa.responsavel = "Bruno Rocha"
        empresa.save()

        admin = User.objects.filter(is_superuser=True).first()
        for nome, sitio, preco, media in PRODUTORES:
            produtor, _ = Produtor.objects.get_or_create(
                nome=nome, defaults={"apelido_propriedade": sitio, "preco_litro": Decimal(preco),
                                     "telefone": f"(27) 9{random.randint(8000, 9999)}-{random.randint(1000, 9999)}"},
            )
            for dias_atras in range(90, 0, -1):
                data = hoje - datetime.timedelta(days=dias_atras)
                if Coleta.objects.filter(produtor=produtor, data=data).exists():
                    continue
                falta = random.random() < 0.04
                litros = Decimal("0") if falta else Decimal(str(round(media * random.uniform(0.8, 1.2), 1)))
                Coleta.objects.create(
                    produtor=produtor, data=data, litros=litros, preco_litro=produtor.preco_litro,
                    forma=random.choice([FormaColeta.COLETADO, FormaColeta.ENTREGUE]), usuario=admin,
                )
        # Hoje: só alguns já lançados (para aparecer a lista de pendentes)
        for produtor in Produtor.objects.all()[:4]:
            if not Coleta.objects.filter(produtor=produtor, data=hoje).exists():
                Coleta.objects.create(produtor=produtor, data=hoje, litros=Decimal("100.0"),
                                      preco_litro=produtor.preco_litro, forma=FormaColeta.COLETADO, usuario=admin)

        # Pagamentos dos meses fechados
        if not leite_servicos.PagamentoProdutor.objects.exists():
            for produtor in Produtor.objects.all():
                for meses_atras in (2, 1):
                    ref = (hoje.replace(day=1) - datetime.timedelta(days=28 * meses_atras)).replace(day=1)
                    fim = (ref.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
                    resumo = leite_servicos.resumo_periodo(produtor, ref, fim)
                    if resumo["total_valor"] > 0:
                        leite_servicos.registrar_pagamento(
                            produtor=produtor, valor=resumo["total_valor"], data=fim + datetime.timedelta(days=5),
                            forma_pagamento="PIX", usuario=admin, periodo_inicio=ref, periodo_fim=fim,
                        )

        # Caixa: algumas entradas e saídas
        if Lancamento.objects.filter(pagamento_produtor__isnull=True).count() < 10:
            entradas = list(Categoria.objects.filter(tipo=TipoLancamento.ENTRADA, sistema=False))
            saidas = list(Categoria.objects.filter(tipo=TipoLancamento.SAIDA, sistema=False))
            for dias_atras in range(0, 150, 3):
                data = hoje - datetime.timedelta(days=dias_atras)
                Lancamento.objects.create(tipo=TipoLancamento.ENTRADA, categoria=random.choice(entradas[:5]),
                                          valor=Decimal(random.randint(400, 3500)), data=data,
                                          descricao="Venda (exemplo)", usuario=admin)
                Lancamento.objects.create(tipo=TipoLancamento.SAIDA, categoria=random.choice(saidas),
                                          valor=Decimal(random.randint(50, 900)), data=data,
                                          descricao="Despesa (exemplo)", usuario=admin)

        if options["usuarios"]:
            configurar_grupos_padrao()
            for login, senha, nivel in (("gerente", "Gerente@2026", "Gerente"),
                                        ("escritorio", "Escritorio@2026", "Escritório"),
                                        ("coletor", "Coletor@2026", "Coletor")):
                usuario, criado = User.objects.get_or_create(username=login, defaults={"first_name": login.title()})
                if criado:
                    usuario.set_password(senha)
                    usuario.save()
                usuario.groups.set([Group.objects.get(name=nivel)])
                Perfil.objects.update_or_create(usuario=usuario, defaults={"deve_trocar_senha": False})
            self.stdout.write("Usuários: gerente/Gerente@2026, escritorio/Escritorio@2026, coletor/Coletor@2026")
        self.stdout.write(self.style.SUCCESS("Dados de exemplo criados."))
