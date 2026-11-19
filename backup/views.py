"""
backup/views.py
===============
Tela de backup: configurar e-mail/horário, enviar agora, baixar e ver o histórico.
"""

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import servicos
from .forms import ConfiguracaoBackupForm
from .models import ConfiguracaoBackup, RegistroBackup


@permission_required("backup.gerenciar_backup", raise_exception=True)
def painel(request):
    config = ConfiguracaoBackup.obter()
    form = ConfiguracaoBackupForm(request.POST or None, instance=config)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Configuração de backup salva.")
        return redirect("backup:painel")
    arquivos = [{"nome": a.name, "tamanho": a.stat().st_size} for a in servicos.listar_arquivos()]
    return render(request, "backup/painel.html", {
        "form": form, "config": config, "arquivos": arquivos,
        "historico": RegistroBackup.objects.select_related("usuario")[:15],
    })


@require_POST
@permission_required("backup.gerenciar_backup", raise_exception=True)
def enviar(request):
    registro = servicos.fazer_backup(origem=RegistroBackup.Origem.MANUAL, enviar=True, usuario=request.user)
    (messages.success if registro.sucesso else messages.error)(request, registro.mensagem)
    return redirect("backup:painel")


@require_POST
@permission_required("backup.gerenciar_backup", raise_exception=True)
def baixar_novo(request):
    """Gera um backup agora e já devolve o arquivo para download."""
    registro = servicos.fazer_backup(origem=RegistroBackup.Origem.DOWNLOAD, usuario=request.user)
    if not registro.sucesso:
        messages.error(request, registro.mensagem)
        return redirect("backup:painel")
    caminho = servicos.caminho_seguro(registro.arquivo)
    return FileResponse(open(caminho, "rb"), as_attachment=True, filename=caminho.name)


@permission_required("backup.gerenciar_backup", raise_exception=True)
def baixar_arquivo(request, nome):
    """Baixa um backup já existente. O nome é conferido contra a lista (sem path traversal)."""
    caminho = servicos.caminho_seguro(nome)
    if caminho is None:
        raise Http404
    return FileResponse(open(caminho, "rb"), as_attachment=True, filename=caminho.name)
