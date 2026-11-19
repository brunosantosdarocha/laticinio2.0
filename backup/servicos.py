"""
backup/servicos.py
==================
Criação, envio e controle dos backups.

O arquivo .zip contém:
- banco.sqlite3 ... cópia exata do banco (feita pela API de backup do SQLite, segura com o sistema em uso);
- dados.json ...... os mesmos dados em JSON (dumpdata), útil para migrar para outro banco;
- logs/ ........... logs de segurança;
- LEIA-ME.txt ..... como restaurar.
O .env (com a SECRET_KEY) NUNCA vai no backup.
"""

import datetime
import io
import logging
import smtplib
import socket
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from .models import ConfiguracaoBackup, RegistroBackup

logger = logging.getLogger("laticinio")

LEIA_ME = """BACKUP DO SISTEMA DO LATICÍNIO
================================
Gerado em: {data}

Como restaurar (com o sistema DESLIGADO):
  1. Copie este .zip para a pasta do sistema.
  2. Rode no terminal:  .venv\\Scripts\\python.exe manage.py restaurar_backup NOME_DO_ARQUIVO.zip
     (no Linux: .venv/bin/python manage.py restaurar_backup NOME_DO_ARQUIVO.zip)
  3. Inicie o sistema de novo com: python iniciar.py

Arquivos:
  banco.sqlite3  -> banco de dados completo
  dados.json     -> os mesmos dados em formato JSON
  logs/          -> registros de segurança
Observação: o arquivo .env não vai no backup. Guarde uma cópia dele em lugar seguro.
"""


def pasta_backups():
    pasta = Path(settings.PASTA_BACKUPS)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def copiar_banco_sqlite(destino):
    """Copia o banco usando a API de backup do SQLite (não corrompe mesmo com o sistema aberto)."""
    connection.ensure_connection()
    origem = connection.connection
    with sqlite3.connect(destino) as copia:
        origem.backup(copia)
    copia.close()


def criar_arquivo_backup():
    """Gera o .zip na pasta backups/ e devolve o caminho."""
    agora = timezone.localtime()
    nome = f"backup_laticinio_{agora:%Y-%m-%d_%H%M%S}.zip"
    caminho = pasta_backups() / nome
    with tempfile.TemporaryDirectory() as temporaria:
        banco_temp = Path(temporaria) / "banco.sqlite3"
        copiar_banco_sqlite(banco_temp)
        dados_json = io.StringIO()
        call_command(
            "dumpdata", exclude=["contenttypes", "auth.permission", "sessions", "admin.logentry", "axes"],
            natural_foreign=True, natural_primary=True, indent=1, stdout=dados_json,
        )
        with zipfile.ZipFile(caminho, "w", compression=zipfile.ZIP_DEFLATED) as zip_:
            zip_.write(banco_temp, "banco.sqlite3")
            zip_.writestr("dados.json", dados_json.getvalue())
            zip_.writestr("LEIA-ME.txt", LEIA_ME.format(data=f"{agora:%d/%m/%Y %H:%M}"))
            pasta_logs = Path(settings.PASTA_LOGS)
            if pasta_logs.exists():
                for log in pasta_logs.glob("*.log*"):
                    zip_.write(log, f"logs/{log.name}")
    limpar_antigos()
    return caminho


def listar_arquivos():
    """Backups da pasta, do mais novo para o mais antigo."""
    return sorted(pasta_backups().glob("backup_laticinio_*.zip"), key=lambda p: p.name, reverse=True)


def limpar_antigos(manter=None):
    """Mantém só os N backups mais recentes (padrão: 10)."""
    manter = manter or settings.BACKUPS_MANTIDOS
    for antigo in listar_arquivos()[manter:]:
        antigo.unlink(missing_ok=True)


def caminho_seguro(nome):
    """Só devolve o arquivo se ele estiver na LISTA de backups (bloqueia '../../.env' e afins)."""
    for arquivo in listar_arquivos():
        if arquivo.name == nome:
            return arquivo
    return None


def mensagem_erro_smtp(erro):
    """Traduz erros de e-mail em mensagens que o usuário entende."""
    if isinstance(erro, smtplib.SMTPAuthenticationError):
        return ("O servidor de e-mail recusou o usuário/senha. No Gmail é preciso usar uma 'senha de app' "
                "(veja as instruções nesta tela), e não a senha normal da conta.")
    if isinstance(erro, (socket.gaierror, ConnectionRefusedError)):
        return "Não foi possível conectar ao servidor SMTP. Confira o endereço, a porta e a internet."
    if isinstance(erro, (socket.timeout, TimeoutError)):
        return "O servidor de e-mail demorou demais para responder. Tente de novo mais tarde."
    if isinstance(erro, smtplib.SMTPRecipientsRefused):
        return "O e-mail de destino foi recusado. Confira o endereço."
    if isinstance(erro, smtplib.SMTPException):
        return f"Erro do servidor de e-mail: {erro}"
    return f"Erro ao enviar o e-mail: {erro}"


def enviar_por_email(config, caminho):
    """Envia o .zip como anexo usando o SMTP configurado na tela."""
    conexao = get_connection(
        host=config.smtp_host, port=config.smtp_porta, username=config.smtp_usuario,
        password=config.obter_senha(), use_tls=config.smtp_tls, timeout=settings.EMAIL_TIMEOUT,
    )
    mensagem = EmailMessage(
        subject=f"Backup do laticínio - {timezone.localtime():%d/%m/%Y %H:%M}",
        body="Segue em anexo o backup automático do sistema do laticínio.\nGuarde este e-mail.",
        from_email=config.smtp_usuario, to=[config.email_destino], connection=conexao,
    )
    mensagem.attach_file(str(caminho), mimetype="application/zip")
    mensagem.send(fail_silently=False)


def fazer_backup(*, origem, enviar=False, usuario=None):
    """Cria o backup, envia por e-mail (se pedido) e grava no histórico. Devolve o RegistroBackup."""
    config = ConfiguracaoBackup.obter()
    registro = RegistroBackup(origem=origem, usuario=usuario)
    try:
        caminho = criar_arquivo_backup()
        registro.arquivo = caminho.name
        registro.tamanho = caminho.stat().st_size
        if enviar:
            if not (config.email_destino and config.smtp_configurado):
                raise ValueError("Configure o e-mail de destino e o SMTP antes de enviar.")
            enviar_por_email(config, caminho)
            registro.enviado_para = config.email_destino
            registro.mensagem = "Backup criado e enviado por e-mail."
        else:
            registro.mensagem = "Backup criado."
    except (smtplib.SMTPException, OSError, socket.error) as erro:
        registro.sucesso = False
        registro.mensagem = mensagem_erro_smtp(erro) if enviar else f"Erro ao criar o backup: {erro}"
        logger.warning("Falha no backup: %s", erro)
    except ValueError as erro:
        registro.sucesso = False
        registro.mensagem = str(erro)
    registro.save()
    return registro


def deve_executar(config, agora):
    """Função pura: decide se o backup automático deve rodar AGORA.

    Roda se já passou do horário de hoje (ou do de ontem) e ainda não foi feito desde então.
    Assim, se o computador estava desligado na hora marcada, o backup é feito assim que ligar.
    """
    if not (config.ativo and config.email_destino):
        return False
    fuso = timezone.get_current_timezone()
    agora = timezone.localtime(agora, fuso)
    horario_hoje = timezone.make_aware(datetime.datetime.combine(agora.date(), config.horario), fuso)
    if config.ultimo_backup_auto is None:
        return agora >= horario_hoje
    alvo = horario_hoje if agora >= horario_hoje else horario_hoje - datetime.timedelta(days=1)
    return config.ultimo_backup_auto < alvo


def executar_agendado(agora=None):
    """Chamado pelo agendador a cada minuto."""
    agora = agora or timezone.now()
    config = ConfiguracaoBackup.obter()
    if not deve_executar(config, agora):
        return None
    registro = fazer_backup(origem=RegistroBackup.Origem.AUTOMATICO, enviar=True)
    # Marca como feito mesmo se o envio falhar, para não tentar a cada minuto (tenta de novo amanhã).
    ConfiguracaoBackup.objects.filter(pk=1).update(ultimo_backup_auto=agora)
    return registro
