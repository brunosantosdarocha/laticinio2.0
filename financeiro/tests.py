"""financeiro/tests.py - caixa: lançamentos, estorno, categorias e totais."""

import datetime
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase

from contas.servicos import configurar_grupos_padrao
from financeiro import servicos
from financeiro.models import Categoria, Lancamento, TipoLancamento
from leite import servicos as leite_servicos
from leite.models import Produtor


class FinanceiroTests(TestCase):
    def setUp(self):
        configurar_grupos_padrao()
        self.admin = User.objects.create_superuser("chefe", "", "Senha@Forte123")
        self.queijo = Categoria.objects.get(nome="Queijos", tipo=TipoLancamento.ENTRADA)
        self.diesel = Categoria.objects.get(nome="Combustivel / Diesel", tipo=TipoLancamento.SAIDA)

    def test_categorias_do_sistema_antigo_existem(self):
        self.assertEqual(Categoria.objects.filter(tipo=TipoLancamento.ENTRADA).count(), 10)
        self.assertTrue(Categoria.objects.filter(nome="Pagamento a produtores", sistema=True).exists())

    def test_lancar_pela_tela(self):
        self.client.force_login(self.admin)
        resposta = self.client.post("/financeiro/novo/entrada/", {
            "data": "2026-03-10", "categoria": self.queijo.pk, "valor": "150.75", "descricao": "Feira",
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Lancamento.objects.get().valor, Decimal("150.75"))

    def test_categoria_do_tipo_errado_e_valor_zero(self):
        with self.assertRaises(ValidationError):
            servicos.criar_lancamento(tipo=TipoLancamento.ENTRADA, categoria=self.diesel, valor=10, data=datetime.date.today())
        with self.assertRaises(ValidationError):
            servicos.criar_lancamento(tipo=TipoLancamento.ENTRADA, categoria=self.queijo, valor=0, data=datetime.date.today())
        self.client.force_login(self.admin)
        self.client.post("/financeiro/novo/entrada/", {"data": "2026-03-10", "categoria": self.diesel.pk, "valor": "10"})
        self.assertFalse(Lancamento.objects.exists())

    def test_totais_ignoram_estornados(self):
        hoje = datetime.date(2026, 3, 10)
        servicos.criar_lancamento(tipo="ENTRADA", categoria=self.queijo, valor=1000, data=hoje)
        saida = servicos.criar_lancamento(tipo="SAIDA", categoria=self.diesel, valor=300, data=hoje)
        servicos.criar_lancamento(tipo="SAIDA", categoria=self.diesel, valor=200, data=hoje)
        servicos.estornar_lancamento(saida, motivo="duplicado", usuario=self.admin)
        totais = servicos.totais_periodo(hoje, hoje)
        self.assertEqual(totais, {"entradas": Decimal("1000"), "saidas": Decimal("200"), "saldo": Decimal("800")})
        with self.assertRaises(ValidationError):
            servicos.estornar_lancamento(saida, motivo="de novo", usuario=self.admin)

    def test_estorno_exige_motivo_e_post(self):
        lanc = servicos.criar_lancamento(tipo="ENTRADA", categoria=self.queijo, valor=10, data=datetime.date.today())
        with self.assertRaises(ValidationError):
            servicos.estornar_lancamento(lanc, motivo="  ", usuario=None)
        self.client.force_login(self.admin)
        self.client.get(f"/financeiro/lancamentos/{lanc.pk}/estornar/")
        lanc.refresh_from_db()
        self.assertFalse(lanc.estornado)

    def test_saida_de_pagamento_so_estorna_pelo_pagamento(self):
        produtor = Produtor.objects.create(nome="Zé")
        pagamento = leite_servicos.registrar_pagamento(produtor=produtor, valor=50, data=datetime.date.today(),
                                                       forma_pagamento="PIX", usuario=None)
        with self.assertRaises(ValidationError):
            servicos.estornar_lancamento(pagamento.lancamento, motivo="teste", usuario=None)

    def test_escritorio_nao_estorna(self):
        lanc = servicos.criar_lancamento(tipo="ENTRADA", categoria=self.queijo, valor=10, data=datetime.date.today())
        usuario = User.objects.create_user("escr", password="Senha@Forte123")
        usuario.groups.add(Group.objects.get(name="Escritório"))
        self.client.force_login(usuario)
        self.assertEqual(self.client.post(f"/financeiro/lancamentos/{lanc.pk}/estornar/", {"motivo": "x"}).status_code, 403)

    def test_extrato_e_dashboard_abrem(self):
        servicos.criar_lancamento(tipo="ENTRADA", categoria=self.queijo, valor=10, data=datetime.date.today())
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/financeiro/").status_code, 200)
        self.assertEqual(self.client.get("/financeiro/?tipo=ENTRADA&q=abc&inicio=2020-01-01").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)
