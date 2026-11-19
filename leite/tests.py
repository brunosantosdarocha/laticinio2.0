"""
leite/tests.py
==============
Testes das regras do leite: coleta diária, calendário, preço em massa, recibo, saldos e pagamentos.
"""

import datetime
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from contas.servicos import configurar_grupos_padrao
from financeiro.models import Lancamento
from leite import servicos
from leite.models import Coleta, FormaColeta, PagamentoProdutor, Produtor


class Base(TestCase):
    def setUp(self):
        configurar_grupos_padrao()
        self.admin = User.objects.create_superuser("chefe", "", "Senha@Forte123")
        self.coletor = User.objects.create_user("coletor", password="Senha@Forte123")
        self.coletor.groups.add(Group.objects.get(name="Coletor"))
        self.produtor = Produtor.objects.create(nome="João", preco_litro=Decimal("2.50"))
        self.hoje = timezone.localdate()


class ColetaDiariaTests(Base):
    def test_coletor_lanca_leite_de_hoje_com_preco_do_cadastro(self):
        self.client.force_login(self.coletor)
        resposta = self.client.post("/leite/coleta-diaria/", {
            "produtor": self.produtor.pk, "forma": "ENTREGUE", "litros": "120.5",
        })
        self.assertEqual(resposta.status_code, 302)
        coleta = Coleta.objects.get()
        self.assertEqual(coleta.data, self.hoje)
        self.assertEqual(coleta.litros, Decimal("120.5"))
        self.assertEqual(coleta.preco_litro, Decimal("2.50"))
        self.assertEqual(coleta.forma, FormaColeta.ENTREGUE)
        self.assertEqual(coleta.usuario, self.coletor)

    def test_coletor_nao_altera_lancamento_existente(self):
        servicos.registrar_coleta_diaria(produtor=self.produtor, litros=100, forma="COLETADO", usuario=self.coletor)
        self.client.force_login(self.coletor)
        self.client.post("/leite/coleta-diaria/", {"produtor": self.produtor.pk, "forma": "COLETADO", "litros": "999"})
        self.assertEqual(Coleta.objects.get().litros, Decimal("100.0"))

    def test_coletor_nao_escolhe_data_nem_preco(self):
        self.client.force_login(self.coletor)
        self.client.post("/leite/coleta-diaria/", {
            "produtor": self.produtor.pk, "forma": "COLETADO", "litros": "50",
            "data": "2020-01-01", "preco_litro": "99",
        })
        coleta = Coleta.objects.get()
        self.assertEqual(coleta.data, self.hoje)
        self.assertEqual(coleta.preco_litro, Decimal("2.50"))

    def test_litros_invalidos(self):
        for litros in (0, -5):
            with self.assertRaises(ValidationError):
                servicos.registrar_coleta_diaria(produtor=self.produtor, litros=litros, forma="COLETADO", usuario=None)

    def test_forma_escritorio_nao_permitida_na_coleta(self):
        with self.assertRaises(ValidationError):
            servicos.registrar_coleta_diaria(produtor=self.produtor, litros=10, forma="ESCRITORIO", usuario=None)

    def test_produtor_inativo(self):
        self.produtor.ativo = False
        self.produtor.save()
        with self.assertRaises(ValidationError):
            servicos.registrar_coleta_diaria(produtor=self.produtor, litros=10, forma="COLETADO", usuario=None)

    def test_pagina_nao_mostra_preco(self):
        servicos.registrar_coleta_diaria(produtor=self.produtor, litros=100, forma="COLETADO", usuario=self.coletor)
        self.client.force_login(self.coletor)
        conteudo = self.client.get("/leite/coleta-diaria/").content.decode()
        self.assertIn("João", conteudo)
        self.assertNotIn("R$", conteudo)

    def test_coletor_nao_edita_nem_exclui(self):
        coleta = servicos.registrar_coleta_diaria(produtor=self.produtor, litros=100, forma="COLETADO", usuario=self.coletor)
        self.client.force_login(self.coletor)
        self.assertEqual(self.client.get(f"/leite/coletas/{coleta.pk}/editar/").status_code, 403)
        self.assertEqual(self.client.post(f"/leite/coletas/{coleta.pk}/excluir/").status_code, 403)
        self.assertEqual(self.client.post("/leite/calendario/?produtor=1", {"dia_1": "5"}).status_code, 403)


class CalendarioTests(Base):
    def test_salvar_criar_alterar_remover_e_falta(self):
        Coleta.objects.create(produtor=self.produtor, data=datetime.date(2026, 3, 2), litros=10, preco_litro=Decimal("2.00"))
        Coleta.objects.create(produtor=self.produtor, data=datetime.date(2026, 3, 3), litros=10, preco_litro=Decimal("2.00"))
        contagem = servicos.salvar_calendario(
            produtor=self.produtor, ano=2026, mes=3,
            valores={1: "50", 2: "20,5", 3: "", 4: ""}, faltas={4}, preco_padrao=Decimal("2.70"), usuario=self.admin,
        )
        self.assertEqual(contagem, {"criados": 2, "alterados": 1, "removidos": 1})
        dia1 = Coleta.objects.get(data="2026-03-01")
        self.assertEqual(dia1.preco_litro, Decimal("2.70"))
        dia2 = Coleta.objects.get(data="2026-03-02")
        self.assertEqual(dia2.litros, Decimal("20.5"))
        self.assertEqual(dia2.preco_litro, Decimal("2.00"))  # mantém o preço antigo
        self.assertFalse(Coleta.objects.filter(data="2026-03-03").exists())
        self.assertTrue(Coleta.objects.get(data="2026-03-04").falta)

    def test_erro_desfaz_tudo(self):
        with self.assertRaises(ValidationError):
            servicos.salvar_calendario(produtor=self.produtor, ano=2026, mes=3, valores={1: "10", 2: "abc"},
                                       faltas=set(), preco_padrao=2, usuario=None)
        self.assertFalse(Coleta.objects.exists())

    def test_tela_salva(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(f"/leite/calendario/?produtor={self.produtor.pk}&mes=2&ano=2026",
                                    {"dia_10": "33.3", "preco_padrao": "2.40"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Coleta.objects.get().litros, Decimal("33.3"))

    def test_preco_em_massa(self):
        outro = Produtor.objects.create(nome="Ana")
        for p in (self.produtor, outro):
            Coleta.objects.create(produtor=p, data=datetime.date(2026, 3, 1), litros=10, preco_litro=Decimal("2.00"))
            Coleta.objects.create(produtor=p, data=datetime.date(2026, 3, 2), litros=10, preco_litro=Decimal("2.20"))
        n = servicos.atualizar_preco_em_massa(produtor=self.produtor, inicio=datetime.date(2026, 3, 1),
                                              fim=datetime.date(2026, 3, 31), preco_atual=Decimal("2.00"), novo_preco=Decimal("2.30"))
        self.assertEqual(n, 1)
        n = servicos.atualizar_preco_em_massa(produtor=None, inicio=datetime.date(2026, 3, 1),
                                              fim=datetime.date(2026, 3, 31), preco_atual=None, novo_preco=Decimal("3.00"))
        self.assertEqual(n, 4)
        with self.assertRaises(ValidationError):
            servicos.atualizar_preco_em_massa(produtor=None, inicio=datetime.date(2026, 4, 1),
                                              fim=datetime.date(2026, 3, 1), preco_atual=None, novo_preco=1)


class ReciboSaldoPagamentoTests(Base):
    def setUp(self):
        super().setUp()
        Coleta.objects.create(produtor=self.produtor, data=datetime.date(2026, 3, 1), litros=Decimal("100.0"), preco_litro=Decimal("2.50"))
        Coleta.objects.create(produtor=self.produtor, data=datetime.date(2026, 3, 2), litros=Decimal("0"), preco_litro=Decimal("2.50"))
        Coleta.objects.create(produtor=self.produtor, data=datetime.date(2026, 3, 3), litros=Decimal("33.3"), preco_litro=Decimal("2.33"))

    def test_resumo_do_recibo(self):
        resumo = servicos.resumo_periodo(self.produtor, datetime.date(2026, 3, 1), datetime.date(2026, 3, 31))
        self.assertEqual(resumo["total_litros"], Decimal("133.3"))
        self.assertEqual(resumo["total_valor"], Decimal("327.59"))  # 250,00 + 0 + 77,59
        self.assertEqual(resumo["faltas"], 1)

    def test_pdf_e_impressao(self):
        self.produtor.telefone = "(27) 99999-0000"
        self.produtor.save()
        self.client.force_login(self.admin)
        url = f"?produtor={self.produtor.pk}&inicio=2026-03-01&fim=2026-03-31"
        pdf = self.client.get("/leite/recibo/pdf/" + url)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertContains(self.client.get("/leite/recibo/imprimir/" + url), "FALTA")
        self.assertContains(self.client.get("/leite/recibo/" + url), "wa.me")

    def test_pagamento_gera_saida_e_abate_saldo(self):
        pagamento = servicos.registrar_pagamento(produtor=self.produtor, valor=Decimal("300"), data=self.hoje,
                                                 forma_pagamento="PIX", usuario=self.admin)
        self.assertEqual(pagamento.lancamento.tipo, "SAIDA")
        self.assertEqual(pagamento.lancamento.valor, Decimal("300.00"))
        self.assertEqual(servicos.saldo_do_produtor(self.produtor)["saldo"], Decimal("27.59"))

    def test_estorno_do_pagamento_estorna_o_caixa(self):
        pagamento = servicos.registrar_pagamento(produtor=self.produtor, valor=Decimal("100"), data=self.hoje,
                                                 forma_pagamento="DINHEIRO", usuario=self.admin)
        servicos.estornar_pagamento(pagamento, motivo="valor errado", usuario=self.admin)
        pagamento.refresh_from_db()
        self.assertTrue(pagamento.estornado)
        self.assertTrue(Lancamento.objects.get().estornado)
        self.assertEqual(servicos.saldo_do_produtor(self.produtor)["saldo"], Decimal("327.59"))
        with self.assertRaises(ValidationError):
            servicos.estornar_pagamento(pagamento, motivo="de novo", usuario=self.admin)

    def test_pagamento_misto_precisa_fechar(self):
        with self.assertRaises(ValidationError):
            servicos.registrar_pagamento(produtor=self.produtor, valor=Decimal("100"), data=self.hoje, forma_pagamento="MISTO",
                                         usuario=None, valor_dinheiro=Decimal("40"), valor_pix=Decimal("50"))
        pagamento = servicos.registrar_pagamento(produtor=self.produtor, valor=Decimal("100"), data=self.hoje,
                                                 forma_pagamento="MISTO", usuario=None,
                                                 valor_dinheiro=Decimal("40"), valor_pix=Decimal("60"))
        self.assertEqual(pagamento.valor_pix, Decimal("60.00"))

    def test_nao_apaga_produtor_com_pagamento(self):
        servicos.registrar_pagamento(produtor=self.produtor, valor=Decimal("10"), data=self.hoje,
                                     forma_pagamento="PIX", usuario=None)
        with self.assertRaises(ValidationError):
            servicos.excluir_produtor(self.produtor)

    def test_apagar_produtor_sem_pagamento_leva_historico(self):
        self.client.force_login(self.admin)
        self.client.post(f"/leite/produtores/{self.produtor.pk}/excluir/")
        self.assertFalse(Produtor.objects.exists())
        self.assertFalse(Coleta.objects.exists())

    def test_exclusao_somente_post(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(f"/leite/produtores/{self.produtor.pk}/excluir/").status_code, 405)
        coleta = Coleta.objects.first()
        self.assertEqual(self.client.get(f"/leite/coletas/{coleta.pk}/excluir/").status_code, 405)

    def test_renomear_mantem_historico(self):
        self.client.force_login(self.admin)
        self.client.post(f"/leite/produtores/{self.produtor.pk}/editar/", {"nome": "João Batista", "preco_litro": "2.50", "ativo": "on"})
        self.produtor.refresh_from_db()
        self.assertEqual(self.produtor.nome, "João Batista")
        self.assertEqual(self.produtor.coletas.count(), 3)

    def test_nome_duplicado_e_cpf_invalido(self):
        self.client.force_login(self.admin)
        resposta = self.client.post("/leite/produtores/novo/", {"nome": "joão", "preco_litro": "2", "cpf": "111.111.111-11"})
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("nome", resposta.context["form"].errors)
        self.assertIn("cpf", resposta.context["form"].errors)
        self.assertEqual(PagamentoProdutor.objects.count(), 0)


class ImportarStreamlitTests(TestCase):
    def test_importa_banco_antigo(self):
        import sqlite3
        import tempfile
        from pathlib import Path

        from django.core.management import call_command

        pasta = tempfile.mkdtemp()
        caminho = Path(pasta) / "financeiro.db"
        con = sqlite3.connect(caminho)
        con.execute("CREATE TABLE leite (id_recebimento INTEGER PRIMARY KEY, nome_produtor TEXT, data_recebimento DATE, quantidade_leite INTEGER, valor_leite FLOAT)")
        con.execute("CREATE TABLE financ (id_gastos INTEGER PRIMARY KEY, saida1 FLOAT DEFAULT 0, entrada3 FLOAT DEFAULT 0, observacao_entrada TEXT, observacao_saida TEXT, data DATE)")
        con.executemany("INSERT INTO leite (nome_produtor, data_recebimento, quantidade_leite, valor_leite) VALUES (?,?,?,?)", [
            ("Zé", None, None, None), ("Zé", "2026-01-01", 100, 2.2), ("Zé", "2026-01-02", 0, 2.2), ("Zé", "2026-01-01", 110, 2.3),
        ])
        con.execute("INSERT INTO financ (saida1, entrada3, observacao_entrada, data) VALUES (50, 300, 'queijo', '2026-01-05')")
        con.commit()
        con.close()
        call_command("importar_streamlit", str(caminho), verbosity=0)
        call_command("importar_streamlit", str(caminho), verbosity=0)  # rodar 2x não duplica
        self.assertEqual(Produtor.objects.count(), 1)
        self.assertEqual(Coleta.objects.count(), 2)
        self.assertEqual(Coleta.objects.get(data="2026-01-01").litros, Decimal("110.0"))
        self.assertEqual(Lancamento.objects.count(), 2)
        self.assertEqual(Produtor.objects.get().preco_litro, Decimal("2.20"))


class ColetaOfflineTests(Base):
    """Fila do celular: envio em lote, código único (sem duplicar), datas e permissões."""

    def item(self, **extra):
        import uuid
        dados = {"codigo": str(uuid.uuid4()), "produtor": self.produtor.pk, "forma": "COLETADO",
                 "litros": "45.5", "data": self.hoje.isoformat()}
        dados.update(extra)
        return dados

    def enviar(self, itens, cliente=None):
        import json
        cliente = cliente or self.client
        return cliente.post("/leite/api/coleta/sincronizar/", json.dumps({"itens": itens}),
                            content_type="application/json")

    def test_envio_grava_com_data_do_celular_e_codigo(self):
        self.client.force_login(self.coletor)
        ontem = (self.hoje - datetime.timedelta(days=1)).isoformat()
        item = self.item(data=ontem, forma="ENTREGUE")
        resposta = self.enviar([item])
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["resultados"][0]["status"], "ok")
        coleta = Coleta.objects.get()
        self.assertEqual(coleta.data.isoformat(), ontem)
        self.assertEqual(str(coleta.codigo_offline), item["codigo"])
        self.assertEqual(coleta.preco_litro, Decimal("2.50"))
        self.assertEqual(coleta.usuario, self.coletor)

    def test_reenvio_do_mesmo_codigo_nao_duplica(self):
        self.client.force_login(self.coletor)
        item = self.item()
        self.enviar([item])
        resposta = self.enviar([item])
        self.assertEqual(resposta.json()["resultados"][0]["status"], "repetido")
        self.assertEqual(Coleta.objects.count(), 1)

    def test_conflito_com_lancamento_do_escritorio_e_recusado(self):
        Coleta.objects.create(produtor=self.produtor, data=self.hoje, litros=10, preco_litro=Decimal("2.50"))
        self.client.force_login(self.coletor)
        resultado = self.enviar([self.item()]).json()["resultados"][0]
        self.assertEqual(resultado["status"], "erro")
        self.assertIn("já tem", resultado["mensagem"])
        self.assertEqual(Coleta.objects.count(), 1)

    def test_datas_fora_da_janela(self):
        from django.conf import settings
        self.client.force_login(self.coletor)
        antiga = (self.hoje - datetime.timedelta(days=settings.COLETA_OFFLINE_DIAS + 1)).isoformat()
        futura = (self.hoje + datetime.timedelta(days=1)).isoformat()
        limite = (self.hoje - datetime.timedelta(days=settings.COLETA_OFFLINE_DIAS)).isoformat()
        resultados = self.enviar([self.item(data=antiga), self.item(data=futura), self.item(data=limite)]).json()["resultados"]
        self.assertEqual([r["status"] for r in resultados], ["erro", "erro", "ok"])

    def test_itens_invalidos_nao_derrubam_o_lote(self):
        self.client.force_login(self.coletor)
        outro = Produtor.objects.create(nome="Ana")
        itens = [self.item(codigo="xyz"), self.item(produtor=99999), self.item(litros="-3"),
                 self.item(forma="ESCRITORIO"), self.item(data="ontem"), self.item(produtor=outro.pk)]
        resultados = self.enviar(itens).json()["resultados"]
        self.assertEqual([r["status"] for r in resultados], ["erro"] * 5 + ["ok"])

    def test_sem_login_responde_401_json_e_nao_grava(self):
        resposta = self.enviar([self.item()])
        self.assertEqual(resposta.status_code, 401)
        self.assertFalse(resposta.json()["autenticado"])
        self.assertFalse(Coleta.objects.exists())

    def test_sem_permissao_403(self):
        semperm = User.objects.create_user("visitante", password="Senha@Forte123")
        self.client.force_login(semperm)
        self.assertEqual(self.enviar([self.item()]).status_code, 403)
        self.assertEqual(self.client.get("/leite/api/coleta/estado/").status_code, 403)

    def test_csrf_obrigatorio_na_api(self):
        from django.test import Client
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.coletor)
        self.assertEqual(self.enviar([self.item()], cliente).status_code, 403)
        token = cliente.get("/leite/api/coleta/estado/").json()["csrf"]
        import json
        resposta = cliente.post("/leite/api/coleta/sincronizar/", json.dumps({"itens": [self.item()]}),
                                content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(resposta.status_code, 200)

    def test_limite_de_itens_e_formato(self):
        from django.conf import settings
        self.client.force_login(self.coletor)
        muitos = [self.item() for _ in range(settings.COLETA_OFFLINE_MAX_ITENS + 1)]
        self.assertEqual(self.enviar(muitos).status_code, 400)
        resposta = self.client.post("/leite/api/coleta/sincronizar/", "nao é json", content_type="application/json")
        self.assertEqual(resposta.status_code, 400)

    def test_estado_nao_mostra_preco(self):
        self.client.force_login(self.coletor)
        servicos.registrar_coleta_diaria(produtor=self.produtor, litros=10, forma="COLETADO", usuario=self.coletor)
        resposta = self.client.get("/leite/api/coleta/estado/")
        self.assertEqual(resposta.json()["usuario"], "coletor")
        self.assertNotIn("preco", resposta.content.decode())
        self.assertEqual(resposta["Cache-Control"].split(",")[0].strip(), "max-age=0")

    def test_senha_provisoria_bloqueia_api_com_json(self):
        from contas.models import Perfil
        Perfil.objects.filter(usuario=self.coletor).update(deve_trocar_senha=True)
        self.client.force_login(self.coletor)
        resposta = self.enviar([self.item()])
        self.assertEqual(resposta.status_code, 403)
        self.assertIn("senha", resposta.json()["erro"])

    def test_service_worker_e_manifest_sem_login(self):
        import json
        sw = self.client.get("/leite/coleta-diaria/sw.js")
        self.assertEqual(sw.status_code, 200)
        self.assertEqual(sw["Content-Type"], "application/javascript")
        self.assertIn("coleta-fila.js", sw.content.decode())
        manifest = self.client.get("/leite/coleta-diaria/manifest.webmanifest")
        self.assertEqual(json.loads(manifest.content)["start_url"], "/leite/coleta-diaria/")

    def test_sessao_do_coletor_dura_mais(self):
        from django.conf import settings
        self.client.post("/contas/entrar/", {"username": "coletor", "password": "Senha@Forte123"})
        self.assertEqual(self.client.session.get_expiry_age(), settings.COLETOR_SESSAO_DIAS * 86400)
        outro = self.client_class()
        outro.post("/contas/entrar/", {"username": "chefe", "password": "Senha@Forte123"})
        self.assertEqual(outro.session.get_expiry_age(), settings.SESSION_COOKIE_AGE)
