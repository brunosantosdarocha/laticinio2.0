"""
backup/tests.py
===============
Usa TransactionTestCase: a cópia do SQLite (API de backup) trava dentro da transação do TestCase.
"""

import datetime
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core import mail
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from backup import servicos
from backup.models import ConfiguracaoBackup, RegistroBackup


class BackupTests(TransactionTestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.ajuste = override_settings(PASTA_BACKUPS=Path(self.pasta),
                                        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
        self.ajuste.enable()
        self.admin = User.objects.create_superuser("chefe", "", "Senha@Forte123")

    def tearDown(self):
        self.ajuste.disable()
        shutil.rmtree(self.pasta, ignore_errors=True)

    def configurar(self):
        config = ConfiguracaoBackup.obter()
        config.email_destino = "dono@exemplo.com"
        config.smtp_usuario = "remetente@exemplo.com"
        config.definir_senha("abcd efgh")
        config.ativo = True
        config.save()
        return config

    def test_senha_fica_criptografada(self):
        config = self.configurar()
        self.assertNotIn("abcd", config.smtp_senha_cifrada)
        self.assertEqual(ConfiguracaoBackup.obter().obter_senha(), "abcd efgh")

    def test_conteudo_do_zip_sem_env(self):
        caminho = servicos.criar_arquivo_backup()
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
        self.assertIn("banco.sqlite3", nomes)
        self.assertIn("dados.json", nomes)
        self.assertIn("LEIA-ME.txt", nomes)
        self.assertFalse(any(n.endswith(".env") for n in nomes))

    def test_envio_por_email(self):
        self.configurar()
        registro = servicos.fazer_backup(origem=RegistroBackup.Origem.MANUAL, enviar=True)
        self.assertTrue(registro.sucesso, registro.mensagem)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["dono@exemplo.com"])
        self.assertEqual(len(mail.outbox[0].attachments), 1)

    def test_envio_sem_configuracao_falha_com_mensagem(self):
        registro = servicos.fazer_backup(origem=RegistroBackup.Origem.MANUAL, enviar=True)
        self.assertFalse(registro.sucesso)
        self.assertIn("Configure", registro.mensagem)

    def test_mantem_so_os_ultimos(self):
        for i in range(12):
            (Path(self.pasta) / f"backup_laticinio_2026-01-{i + 1:02d}_000000.zip").write_bytes(b"x")
        servicos.limpar_antigos(10)
        self.assertEqual(len(servicos.listar_arquivos()), 10)

    def test_path_traversal_bloqueado(self):
        self.client.force_login(self.admin)
        caminho = servicos.criar_arquivo_backup()
        self.assertEqual(self.client.get(f"/backup/arquivo/{caminho.name}/").status_code, 200)
        self.assertEqual(self.client.get("/backup/arquivo/..%2F.env/").status_code, 404)
        self.assertIsNone(servicos.caminho_seguro("../.env"))
        self.assertIsNone(servicos.caminho_seguro("db.sqlite3"))

    def test_regra_do_agendador(self):
        fuso = timezone.get_current_timezone()
        config = ConfiguracaoBackup(ativo=True, email_destino="a@b.com", horario=datetime.time(22, 0))
        hora = lambda d, h, m=0: timezone.make_aware(datetime.datetime(2026, 3, d, h, m), fuso)
        # Nunca fez: antes do horário não roda; depois roda
        self.assertFalse(servicos.deve_executar(config, hora(10, 21)))
        self.assertTrue(servicos.deve_executar(config, hora(10, 22, 1)))
        # Fez ontem às 22h: hoje às 10h não roda; às 22h roda
        config.ultimo_backup_auto = hora(9, 22, 1)
        self.assertFalse(servicos.deve_executar(config, hora(10, 10)))
        self.assertTrue(servicos.deve_executar(config, hora(10, 22, 5)))
        # Computador desligado ontem à noite: liga hoje de manhã -> roda (atrasado)
        config.ultimo_backup_auto = hora(8, 22, 1)
        self.assertTrue(servicos.deve_executar(config, hora(10, 8)))
        # Desligado: nunca roda
        config.ativo = False
        self.assertFalse(servicos.deve_executar(config, hora(10, 23)))
