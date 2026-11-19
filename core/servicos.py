"""
core/servicos.py
================
Monta os números do dashboard e os alertas do sininho.
Cada bloco só é calculado se o usuário tiver permissão de ver aquele assunto.
"""

import datetime
from collections import OrderedDict
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from backup.models import ConfiguracaoBackup, RegistroBackup
from core.escolhas import NOMES_MESES
from core.utils import primeiro_dia_mes, ultimos_meses
from financeiro import servicos as financeiro_servicos
from leite import servicos as leite_servicos
from leite.models import Coleta, Produtor


def serie_litros_mensal(meses=6):
    """Litros recebidos por mês (gráfico de área do dashboard)."""
    lista = ultimos_meses(meses)
    dados = OrderedDict((chave, Decimal("0")) for chave in lista)
    ano0, mes0 = lista[0]
    linhas = (
        Coleta.objects.filter(data__gte=f"{ano0:04d}-{mes0:02d}-01")
        .values("data__year", "data__month").annotate(total=Sum("litros"))
    )
    for linha in linhas:
        chave = (linha["data__year"], linha["data__month"])
        if chave in dados:
            dados[chave] = linha["total"]
    return {
        "rotulos": [f"{NOMES_MESES[m - 1][:3]}/{str(a)[2:]}" for a, m in dados],
        "series": [{"rotulo": "Litros recebidos", "dados": [float(v) for v in dados.values()]}],
    }


def rosca_produtores_mes(limite=6):
    """Participação de cada produtor no leite do mês (gráfico de rosca)."""
    hoje = timezone.localdate()
    linhas = list(
        Coleta.objects.filter(data__gte=primeiro_dia_mes(hoje), data__lte=hoje)
        .values("produtor__nome").annotate(total=Sum("litros")).order_by("-total")
    )
    principais = linhas[:limite]
    outros = sum((l["total"] for l in linhas[limite:]), Decimal("0"))
    rotulos = [l["produtor__nome"] for l in principais]
    valores = [float(l["total"]) for l in principais]
    if outros:
        rotulos.append("Outros")
        valores.append(float(outros))
    return {"rotulos": rotulos, "series": [{"rotulo": "Litros", "dados": valores}]}


def dados_dashboard(usuario):
    hoje = timezone.localdate()
    inicio_mes = primeiro_dia_mes(hoje)
    fim_mes_anterior = inicio_mes - datetime.timedelta(days=1)
    inicio_mes_anterior = primeiro_dia_mes(fim_mes_anterior)
    # Mesmo período do mês anterior (dia 1 até o mesmo dia), para comparar de forma justa.
    dia_comparavel = min(hoje.day, fim_mes_anterior.day)
    contexto = {"hoje": hoje}

    litros_mes = leite_servicos.litros_periodo(inicio_mes, hoje)
    litros_mes_anterior = leite_servicos.litros_periodo(
        inicio_mes_anterior, inicio_mes_anterior.replace(day=dia_comparavel)
    )
    variacao = None
    if litros_mes_anterior:
        variacao = ((litros_mes - litros_mes_anterior) / litros_mes_anterior * 100).quantize(Decimal("0.1"))
    contexto.update({
        "litros_hoje": leite_servicos.litros_periodo(hoje, hoje),
        "litros_mes": litros_mes,
        "variacao_mes": variacao,
        "produtores_ativos": Produtor.objects.filter(ativo=True).count(),
        "pendentes_hoje": leite_servicos.produtores_sem_coleta(hoje).count(),
        "grafico_litros": serie_litros_mensal(),
        "grafico_rosca": rosca_produtores_mes(),
        "ultimas_coletas": Coleta.objects.select_related("produtor", "usuario").order_by("-criado_em")[:8],
        "faltas_mes": (
            Produtor.objects.filter(coletas__data__gte=inicio_mes, coletas__litros=0)
            .annotate(qtd=Count("coletas", filter=Q(coletas__data__gte=inicio_mes, coletas__litros=0)))
            .order_by("-qtd")[:5]
        ),
    })
    if usuario.has_perm("leite.view_pagamentoprodutor"):
        saldos = leite_servicos.saldos_produtores()
        contexto["saldo_a_pagar"] = sum((l["saldo"] for l in saldos if l["saldo"] > 0), Decimal("0"))
        contexto["maiores_saldos"] = [l for l in saldos if l["saldo"] > 0][:5]
    if usuario.has_perm("financeiro.view_lancamento"):
        contexto["financeiro_mes"] = financeiro_servicos.totais_periodo(inicio_mes, hoje)
        serie = financeiro_servicos.serie_mensal()
        contexto["grafico_caixa"] = {
            "rotulos": serie["rotulos"],
            "series": [
                {"rotulo": "Entradas", "dados": serie["entradas"]},
                {"rotulo": "Saídas", "dados": serie["saidas"]},
            ],
        }
    return contexto


def alertas_do_usuario(usuario):
    """Itens do sininho da barra superior."""
    alertas = []
    if usuario.has_perm("leite.view_coleta") or usuario.has_perm("leite.registrar_coleta_diaria"):
        pendentes = leite_servicos.produtores_sem_coleta().count()
        if pendentes:
            url = reverse("leite:coleta_diaria") if usuario.has_perm("leite.registrar_coleta_diaria") else reverse("leite:calendario")
            alertas.append({"icone": "bi-droplet", "cor": "text-warning",
                            "texto": f"{pendentes} produtor(es) sem leite lançado hoje", "url": url})
    if usuario.has_perm("backup.gerenciar_backup"):
        config = ConfiguracaoBackup.obter()
        if not config.ativo:
            alertas.append({"icone": "bi-cloud-slash", "cor": "text-danger",
                            "texto": "Backup automático desligado", "url": reverse("backup:painel")})
        ultimo = RegistroBackup.objects.first()
        if ultimo and not ultimo.sucesso:
            alertas.append({"icone": "bi-exclamation-triangle", "cor": "text-danger",
                            "texto": "O último backup falhou", "url": reverse("backup:painel")})
    return alertas
