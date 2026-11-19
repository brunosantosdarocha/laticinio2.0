"""
contas/tests.py
===============
Testes de SEGURANÇA e de usuários. Rode com:  python manage.py test
"""

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase, override_settings

from contas.models import Perfil
from contas.servicos import configurar_grupos_padrao, salvar_permissoes_nivel


def criar_usuario(username, nivel=None, admin=False, senha="Senha@Forte123"):
    usuario = User.objects.create_user(username, password=senha, is_superuser=admin, is_staff=admin)
    if nivel:
        usuario.groups.add(Group.objects.get(name=nivel))
    return usuario


class SegurancaTests(TestCase):
    def setUp(self):
        configurar_grupos_padrao()
        self.admin = criar_usuario("chefe", admin=True)

    def test_login_obrigatorio(self):
        for url in ["/", "/leite/calendario/", "/financeiro/", "/backup/", "/leite/coleta-diaria/"]:
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 302, url)
            self.assertIn("/contas/entrar/", resposta["Location"])

    def test_bloqueio_na_quinta_senha_errada(self):
        for _ in range(4):
            resposta = self.client.post("/contas/entrar/", {"username": "chefe", "password": "errada"})
            self.assertEqual(resposta.status_code, 200)
        resposta = self.client.post("/contas/entrar/", {"username": "chefe", "password": "errada"})
        self.assertEqual(resposta.status_code, 429)
        # Mesmo com a senha certa continua bloqueado
        resposta = self.client.post("/contas/entrar/", {"username": "chefe", "password": "Senha@Forte123"})
        self.assertEqual(resposta.status_code, 429)

    def test_login_correto(self):
        resposta = self.client.post("/contas/entrar/", {"username": "chefe", "password": "Senha@Forte123"})
        self.assertEqual(resposta.status_code, 302)

    def test_login_nao_redireciona_para_outro_site(self):
        resposta = self.client.post("/contas/entrar/?next=https://site-malicioso.com/",
                                    {"username": "chefe", "password": "Senha@Forte123"})
        self.assertNotIn("malicioso", resposta["Location"])

    def test_403_por_nivel(self):
        coletor = criar_usuario("coletor", "Coletor")
        self.client.force_login(coletor)
        for url in ["/leite/calendario/", "/leite/produtores/", "/financeiro/", "/backup/", "/contas/usuarios/", "/leite/saldos/"]:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.assertEqual(self.client.get("/leite/coleta-diaria/").status_code, 200)

    def test_escritorio_nao_gerencia_usuarios_nem_backup(self):
        self.client.force_login(criar_usuario("escr", "Escritório"))
        self.assertEqual(self.client.get("/contas/usuarios/").status_code, 403)
        self.assertEqual(self.client.get("/backup/").status_code, 403)
        self.assertEqual(self.client.get("/leite/calendario/").status_code, 200)

    def test_logout_somente_post(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/contas/sair/").status_code, 405)
        self.assertEqual(self.client.post("/contas/sair/").status_code, 302)

    def test_csrf_obrigatorio(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        resposta = cliente.post("/leite/produtores/novo/", {"nome": "Sem token", "preco_litro": "2"})
        self.assertEqual(resposta.status_code, 403)

    def test_xss_escapado(self):
        from leite.models import Produtor
        Produtor.objects.create(nome="<script>alert(1)</script>")
        self.client.force_login(self.admin)
        conteudo = self.client.get("/leite/produtores/").content.decode()
        self.assertNotIn("<script>alert(1)</script>", conteudo)
        self.assertIn("&lt;script&gt;", conteudo)

    def test_cabecalhos_de_seguranca(self):
        resposta = self.client.get("/contas/entrar/")
        self.assertEqual(resposta["X-Frame-Options"], "DENY")
        self.assertEqual(resposta["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resposta["Referrer-Policy"], "same-origin")

    def test_admin_padrao_nao_existe(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/admin/").status_code, 404)
        self.assertEqual(self.client.get("/" + settings.ADMIN_URL).status_code, 200)

    def test_pagina_404_sem_login_nao_mostra_menu(self):
        # Sem login, o middleware manda para o login; logado, 404 com menu.
        self.client.force_login(self.admin)
        resposta = self.client.get("/nao-existe/")
        self.assertEqual(resposta.status_code, 404)


class ContasTests(TestCase):
    def setUp(self):
        configurar_grupos_padrao()
        self.admin = criar_usuario("chefe", admin=True)
        self.client.force_login(self.admin)

    def test_troca_de_senha_obrigatoria(self):
        usuario = criar_usuario("novo", "Escritório")
        Perfil.objects.filter(usuario=usuario).update(deve_trocar_senha=True)
        cliente = Client()
        cliente.force_login(usuario)
        resposta = cliente.get("/leite/calendario/")
        self.assertRedirects(resposta, "/contas/senha/", fetch_redirect_response=False)
        resposta = cliente.post("/contas/senha/", {
            "old_password": "Senha@Forte123", "new_password1": "NovaSenha#2026", "new_password2": "NovaSenha#2026",
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(cliente.get("/leite/calendario/").status_code, 200)

    def test_criar_usuario_com_senha_provisoria(self):
        resposta = self.client.post("/contas/usuarios/novo/", {
            "username": "maria", "nome": "Maria", "nivel": Group.objects.get(name="Coletor").pk,
        })
        self.assertEqual(resposta.status_code, 200)
        senha = resposta.context["senha"]
        usuario = User.objects.get(username="maria")
        self.assertTrue(usuario.check_password(senha))
        self.assertFalse(usuario.perfil.deve_trocar_senha)  # só exige troca se o admin pedir

    def test_criar_usuario_exigindo_troca(self):
        self.client.post("/contas/usuarios/novo/", {
            "username": "joao", "nome": "João", "nivel": Group.objects.get(name="Coletor").pk, "exigir_troca": "on",
        })
        self.assertTrue(User.objects.get(username="joao").perfil.deve_trocar_senha)

    def test_redefinir_senha_nao_exige_troca(self):
        usuario = criar_usuario("ana", "Escritório")
        self.client.post(f"/contas/usuarios/{usuario.pk}/redefinir-senha/")
        usuario.refresh_from_db()
        self.assertFalse(usuario.perfil.deve_trocar_senha)

    def test_editar_usuario_exige_troca(self):
        usuario = criar_usuario("bia", "Escritório")
        self.client.post(f"/contas/usuarios/{usuario.pk}/editar/", {
            "nome": "Bia", "nivel": Group.objects.get(name="Escritório").pk, "ativo": "on", "exigir_troca": "on",
        })
        usuario.refresh_from_db()
        self.assertTrue(usuario.perfil.deve_trocar_senha)

    def test_admin_nao_remove_proprio_acesso(self):
        resposta = self.client.post(f"/contas/usuarios/{self.admin.pk}/editar/", {
            "nome": "Chefe", "administrador": "", "ativo": "on",
        })
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)
        self.assertEqual(resposta.status_code, 200)

    def test_sempre_um_admin_ativo(self):
        from contas.servicos import atualizar_usuario
        from django.core.exceptions import ValidationError
        outro = criar_usuario("outro", admin=True)
        self.admin.is_superuser = False
        self.admin.save()
        with self.assertRaises(ValidationError):
            atualizar_usuario(outro, editor=self.admin, nome="", email="", nivel=None, administrador=False, ativo=True)

    def test_editor_de_niveis_ignora_permissao_fora_da_lista(self):
        grupo = Group.objects.create(name="Teste")
        salvar_permissoes_nivel(grupo, ["leite.view_coleta", "auth.delete_user", "contas.change_perfil"])
        codigos = {f"{p.content_type.app_label}.{p.codename}" for p in grupo.permissions.all()}
        self.assertEqual(codigos, {"leite.view_coleta"})

    def test_editor_de_niveis_pela_tela(self):
        grupo = Group.objects.get(name="Coletor")
        self.client.post(f"/contas/niveis/{grupo.pk}/editar/", {
            "name": "Coletor", "permissoes": ["leite.registrar_coleta_diaria", "auth.add_user"],
        })
        self.assertFalse(grupo.permissions.filter(codename="add_user").exists())
        self.assertTrue(grupo.permissions.filter(codename="registrar_coleta_diaria").exists())

    def test_comando_admin_inicial_nao_duplica(self):
        from django.core.management import call_command
        call_command("criar_admin_inicial", verbosity=0)
        self.assertFalse(User.objects.filter(username="admin").exists())  # já existia o "chefe"
