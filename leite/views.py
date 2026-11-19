"""
leite/views.py
==============
Telas do leite. Todas as views são FUNÇÕES e seguem o mesmo roteiro:
1. o decorador confere a permissão (sem permissão -> página 403);
2. a view lê/valida o formulário;
3. chama a regra de negócio em servicos.py;
4. mostra uma mensagem e redireciona (para não reenviar o formulário com F5).
"""

import datetime
import json
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.escolhas import NOMES_DIAS_SEMANA, NOMES_MESES
from core.models import DadosEmpresa
from core.templatetags.formatos import litros, moeda
from core.utils import (
    ler_data, ler_inteiro, link_whatsapp, paginar, primeiro_dia_mes, termo_busca, ultimo_dia_mes,
)

from . import servicos
from .forms import (
    ColetaDiariaForm, ColetaEditarForm, EstornoForm, PagamentoForm, PeriodoForm, PrecoMassaForm, ProdutorForm,
)
from .models import Coleta, PagamentoProdutor, Produtor
from .pdf import gerar_pdf_recibo

# Troque este número sempre que mudar o JS/CSS da coleta offline: força os celulares a baixarem a versão nova.
VERSAO_PWA = "1"


def _produtor_da_url(request, nome="produtor"):
    """Lê ?produtor=ID da URL com segurança (ID inválido = nenhum produtor)."""
    pk = ler_inteiro(request.GET.get(nome) or request.POST.get(nome), None, minimo=1)
    return Produtor.objects.filter(pk=pk).first() if pk else None


def _mostrar_erro(request, erro):
    """Mostra todas as mensagens de um ValidationError como alertas vermelhos."""
    for mensagem in erro.messages:
        messages.error(request, mensagem)


# ==============================================================================
# PRODUTORES
# ==============================================================================
@permission_required("leite.view_produtor", raise_exception=True)
def produtores_lista(request):
    """Lista de produtores com busca e filtro de situação."""
    busca = termo_busca(request)
    situacao = request.GET.get("situacao", "ativos")
    produtores = Produtor.objects.all()
    if busca:
        produtores = produtores.filter(
            Q(nome__icontains=busca) | Q(apelido_propriedade__icontains=busca) | Q(cpf__icontains=busca)
        )
    if situacao == "ativos":
        produtores = produtores.filter(ativo=True)
    elif situacao == "inativos":
        produtores = produtores.filter(ativo=False)

    hoje = timezone.localdate()
    produtores = produtores.annotate(
        litros_mes=Sum("coletas__litros", filter=Q(coletas__data__gte=primeiro_dia_mes(hoje), coletas__data__lte=hoje))
    ).order_by("nome")
    return render(request, "leite/produtores_lista.html", {
        "pagina": paginar(request, produtores),
        "busca": busca,
        "situacao": situacao,
    })


@permission_required("leite.add_produtor", raise_exception=True)
def produtor_criar(request):
    form = ProdutorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        produtor = form.save()
        messages.success(request, f"Produtor '{produtor.nome}' cadastrado!")
        return redirect("leite:produtor_detalhe", pk=produtor.pk)
    return render(request, "leite/produtor_form.html", {"form": form, "titulo": "Novo produtor"})


@permission_required("leite.change_produtor", raise_exception=True)
def produtor_editar(request, pk):
    """Editar/renomear. Como o histórico está ligado pelo ID, renomear não perde nada."""
    produtor = get_object_or_404(Produtor, pk=pk)
    form = ProdutorForm(request.POST or None, instance=produtor)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dados do produtor atualizados (o histórico continua o mesmo).")
        return redirect("leite:produtor_detalhe", pk=produtor.pk)
    return render(request, "leite/produtor_form.html", {
        "form": form, "titulo": f"Editar produtor: {produtor.nome}", "produtor": produtor,
    })


@permission_required("leite.view_produtor", raise_exception=True)
def produtor_detalhe(request, pk):
    """Ficha do produtor: dados, saldo, últimos lançamentos e pagamentos."""
    produtor = get_object_or_404(Produtor, pk=pk)
    hoje = timezone.localdate()
    inicio_mes = primeiro_dia_mes(hoje)
    resumo_mes = servicos.resumo_periodo(produtor, inicio_mes, hoje)
    return render(request, "leite/produtor_detalhe.html", {
        "produtor": produtor,
        "saldo": servicos.saldo_do_produtor(produtor),
        "resumo_mes": resumo_mes,
        "ultimas_coletas": produtor.coletas.order_by("-data")[:15],
        "pagamentos": produtor.pagamentos.order_by("-data", "-id")[:10],
        "inicio_mes": inicio_mes,
        "hoje": hoje,
    })


@require_POST
@permission_required("leite.delete_produtor", raise_exception=True)
def produtor_excluir(request, pk):
    produtor = get_object_or_404(Produtor, pk=pk)
    try:
        quantidade = servicos.excluir_produtor(produtor)
    except ValidationError as erro:
        _mostrar_erro(request, erro)
        return redirect("leite:produtor_detalhe", pk=pk)
    messages.success(request, f"Produtor apagado junto com {quantidade} lançamento(s) de leite.")
    return redirect("leite:produtores")


# ==============================================================================
# COLETA DIÁRIA (página do coletor)
# ==============================================================================
@permission_required("leite.registrar_coleta_diaria", raise_exception=True)
def coleta_diaria(request):
    """Página simples para o celular: só INSERE o leite de hoje (coletado ou entregue).

    Não mostra preços, não edita e não apaga. Correções são feitas pelo escritório.
    """
    form = ColetaDiariaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            coleta = servicos.registrar_coleta_diaria(
                produtor=form.cleaned_data["produtor"],
                litros=form.cleaned_data["litros"],
                forma=form.cleaned_data["forma"],
                usuario=request.user,
            )
        except ValidationError as erro:
            _mostrar_erro(request, erro)
        else:
            messages.success(
                request, f"{litros(coleta.litros)} de {coleta.produtor.nome} lançados ({coleta.get_forma_display().lower()})."
            )
            return redirect("leite:coleta_diaria")

    coletas = servicos.coletas_de_hoje().order_by("-criado_em")
    return render(request, "leite/coleta_diaria.html", {
        "form": form,
        "hoje": timezone.localdate(),
        "coletas": coletas,
        "total_hoje": sum((c.litros for c in coletas), Decimal("0")),
        "pendentes": servicos.produtores_sem_coleta(),
        # Estado inicial para o modo offline (coleta-offline.js lê pelo json_script).
        "estado_coleta": _estado_coleta(request),
        "dias_offline": settings.COLETA_OFFLINE_DIAS,
    })


# ==============================================================================
# CALENDÁRIO MENSAL (escritório)
# ==============================================================================
@permission_required("leite.view_coleta", raise_exception=True)
def calendario(request):
    """Calendário do mês de um produtor: digita os litros de cada dia e salva tudo de uma vez."""
    hoje = timezone.localdate()
    produtor = _produtor_da_url(request)
    mes = ler_inteiro(request.GET.get("mes"), hoje.month, 1, 12)
    ano = ler_inteiro(request.GET.get("ano"), hoje.year, 2000, 2100)

    if request.method == "POST":
        if not (request.user.has_perm("leite.add_coleta") and request.user.has_perm("leite.change_coleta")):
            raise PermissionDenied
        if produtor is None:
            messages.error(request, "Escolha um produtor.")
            return redirect("leite:calendario")
        valores = {}
        faltas = set()
        for dia in range(1, 32):
            if f"dia_{dia}" in request.POST:
                valores[dia] = request.POST.get(f"dia_{dia}", "")[:10]
            if request.POST.get(f"falta_{dia}"):
                faltas.add(dia)
        # Quem não pode excluir não consegue "apagar" um dia limpando o campo.
        if not request.user.has_perm("leite.delete_coleta"):
            existentes = servicos.coletas_do_mes(produtor, ano, mes)
            for dia, coleta in existentes.items():
                if not (valores.get(dia) or "").strip() and dia not in faltas:
                    valores[dia] = str(coleta.litros)
        try:
            preco = Decimal((request.POST.get("preco_padrao") or "0").replace(",", "."))
        except ArithmeticError:
            preco = produtor.preco_litro
        try:
            contagem = servicos.salvar_calendario(
                produtor=produtor, ano=ano, mes=mes, valores=valores, faltas=faltas,
                preco_padrao=preco, usuario=request.user,
            )
        except ValidationError as erro:
            _mostrar_erro(request, erro)
        else:
            if any(contagem.values()):
                messages.success(
                    request,
                    f"Calendário salvo: {contagem['criados']} novo(s), {contagem['alterados']} alterado(s), "
                    f"{contagem['removidos']} removido(s).",
                )
            else:
                messages.info(request, "Nenhuma alteração para salvar.")
        return redirect(f"{reverse('leite:calendario')}?produtor={produtor.pk}&mes={mes}&ano={ano}")

    contexto = {
        "produtores": Produtor.objects.order_by("-ativo", "nome"),
        "produtor": produtor,
        "mes": mes,
        "ano": ano,
        "meses": list(enumerate(NOMES_MESES, start=1)),
        "nome_mes": NOMES_MESES[mes - 1],
        "dias_semana": NOMES_DIAS_SEMANA,
    }
    if produtor:
        coletas = servicos.coletas_do_mes(produtor, ano, mes)
        semanas = []
        for semana in servicos.dias_do_mes(ano, mes):
            linha = []
            for indice, dia in enumerate(semana):
                coleta = coletas.get(dia) if dia else None
                linha.append({
                    "dia": dia,
                    "coleta": coleta,
                    "fim_de_semana": indice >= 5,
                    "hoje": dia and datetime.date(ano, mes, dia) == hoje,
                })
            semanas.append(linha)
        lista = sorted(coletas.values(), key=lambda c: c.data)
        # Mês anterior / próximo para os botões de navegação
        anterior = primeiro_dia_mes(datetime.date(ano, mes, 1)) - datetime.timedelta(days=1)
        proximo = ultimo_dia_mes(datetime.date(ano, mes, 1)) + datetime.timedelta(days=1)
        contexto.update({
            "semanas": semanas,
            "historico": lista,
            "total_litros": sum((c.litros for c in lista), Decimal("0")),
            "total_valor": sum((c.valor_total for c in lista), Decimal("0")),
            "faltas": sum(1 for c in lista if c.falta),
            "anterior": anterior,
            "proximo": proximo,
            "form_massa": PrecoMassaForm(initial={
                "filtrar_preco": True,
                "preco_atual": produtor.preco_litro,
                "novo_preco": produtor.preco_litro,
                "inicio": datetime.date(ano, mes, 1),
                "fim": ultimo_dia_mes(datetime.date(ano, mes, 1)),
            }),
        })
    return render(request, "leite/calendario.html", contexto)


@require_POST
@permission_required("leite.alterar_preco_massa", raise_exception=True)
def preco_massa(request):
    """Recebe o formulário de preço em massa (que fica dentro do calendário)."""
    produtor = _produtor_da_url(request)
    mes = ler_inteiro(request.POST.get("mes"), timezone.localdate().month, 1, 12)
    ano = ler_inteiro(request.POST.get("ano"), timezone.localdate().year, 2000, 2100)
    form = PrecoMassaForm(request.POST)
    if form.is_valid():
        dados = form.cleaned_data
        alvo = None if dados["todos_produtores"] else produtor
        if alvo is None and not dados["todos_produtores"]:
            messages.error(request, "Escolha um produtor ou marque 'todos os produtores'.")
        else:
            try:
                quantidade = servicos.atualizar_preco_em_massa(
                    produtor=alvo, inicio=dados["inicio"], fim=dados["fim"],
                    preco_atual=dados["preco_atual"] if dados["filtrar_preco"] else None,
                    novo_preco=dados["novo_preco"],
                )
            except ValidationError as erro:
                _mostrar_erro(request, erro)
            else:
                if quantidade:
                    messages.success(request, f"{quantidade} registro(s) atualizado(s) para {moeda(dados['novo_preco'])}/L.")
                else:
                    messages.warning(request, "Nenhum registro correspondeu aos filtros escolhidos. Nada foi alterado.")
    else:
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
    destino = reverse("leite:calendario") + f"?mes={mes}&ano={ano}"
    if produtor:
        destino += f"&produtor={produtor.pk}"
    return redirect(destino)


@permission_required("leite.change_coleta", raise_exception=True)
def coleta_editar(request, pk):
    coleta = get_object_or_404(Coleta.objects.select_related("produtor"), pk=pk)
    form = ColetaEditarForm(request.POST or None, instance=coleta)
    voltar = f"{reverse('leite:calendario')}?produtor={coleta.produtor_id}&mes={coleta.data.month}&ano={coleta.data.year}"
    if request.method == "POST" and form.is_valid():
        try:
            servicos.editar_coleta(
                coleta, litros=form.cleaned_data["litros"], preco_litro=form.cleaned_data["preco_litro"],
                forma=form.cleaned_data["forma"], usuario=request.user,
            )
        except ValidationError as erro:
            _mostrar_erro(request, erro)
        else:
            messages.success(request, "Lançamento corrigido.")
            return redirect(voltar)
    return render(request, "leite/coleta_form.html", {"form": form, "coleta": coleta, "voltar": voltar})


@require_POST
@permission_required("leite.delete_coleta", raise_exception=True)
def coleta_excluir(request, pk):
    coleta = get_object_or_404(Coleta, pk=pk)
    voltar = f"{reverse('leite:calendario')}?produtor={coleta.produtor_id}&mes={coleta.data.month}&ano={coleta.data.year}"
    coleta.delete()
    messages.success(request, "Lançamento removido.")
    return redirect(voltar)


# ==============================================================================
# RECIBO
# ==============================================================================
def _dados_recibo(request):
    """Lê produtor + período da URL e monta o resumo. Usado pelas 3 telas do recibo."""
    produtor = _produtor_da_url(request)
    inicio_padrao, fim_padrao = PeriodoForm.periodo_padrao()
    form = PeriodoForm(request.GET or None, initial={"inicio": inicio_padrao, "fim": fim_padrao})
    if request.GET.get("inicio") or request.GET.get("fim"):
        if not form.is_valid():
            return produtor, form, None, None, None
        inicio, fim = form.cleaned_data["inicio"], form.cleaned_data["fim"]
    else:
        form = PeriodoForm(initial={"inicio": inicio_padrao, "fim": fim_padrao})
        inicio, fim = inicio_padrao, fim_padrao
    resumo = servicos.resumo_periodo(produtor, inicio, fim) if produtor else None
    return produtor, form, inicio, fim, resumo


@permission_required("leite.emitir_recibo", raise_exception=True)
def recibo(request):
    produtor, form, inicio, fim, resumo = _dados_recibo(request)
    contexto = {
        "produtores": Produtor.objects.order_by("-ativo", "nome"),
        "produtor": produtor, "form": form, "inicio": inicio, "fim": fim, "resumo": resumo,
    }
    if produtor and resumo is not None:
        if not resumo["coletas"]:
            # Diagnóstico (igual ao sistema antigo): existe leite fora do período?
            todas = produtor.coletas.order_by("data")
            contexto["fora_do_periodo"] = {
                "quantidade": todas.count(),
                "primeira": todas.first().data if todas.exists() else None,
                "ultima": todas.last().data if todas.exists() else None,
            }
        empresa = DadosEmpresa.obter()
        contexto["link_whatsapp"] = link_whatsapp(
            produtor.telefone, servicos.texto_whatsapp_recibo(produtor, inicio, fim, resumo, empresa.nome)
        )
        contexto["parametros"] = f"produtor={produtor.pk}&inicio={inicio:%Y-%m-%d}&fim={fim:%Y-%m-%d}"
    return render(request, "leite/recibo.html", contexto)


@permission_required("leite.emitir_recibo", raise_exception=True)
def recibo_imprimir(request):
    produtor, _form, inicio, fim, resumo = _dados_recibo(request)
    if not produtor or resumo is None:
        messages.error(request, "Escolha o produtor e um período válido.")
        return redirect("leite:recibo")
    return render(request, "leite/recibo_imprimir.html", {
        "empresa": DadosEmpresa.obter(), "produtor": produtor, "inicio": inicio, "fim": fim,
        "resumo": resumo, "emissao": timezone.localdate(),
    })


@permission_required("leite.emitir_recibo", raise_exception=True)
def recibo_pdf(request):
    produtor, _form, inicio, fim, resumo = _dados_recibo(request)
    if not produtor or resumo is None:
        messages.error(request, "Escolha o produtor e um período válido.")
        return redirect("leite:recibo")
    conteudo = gerar_pdf_recibo(empresa=DadosEmpresa.obter(), produtor=produtor, inicio=inicio, fim=fim, resumo=resumo)
    nome_arquivo = "".join(ch if ch.isalnum() else "_" for ch in produtor.nome)
    resposta = HttpResponse(conteudo, content_type="application/pdf")
    resposta["Content-Disposition"] = f'attachment; filename="Recibo_{nome_arquivo}_{inicio:%Y-%m-%d}_a_{fim:%Y-%m-%d}.pdf"'
    return resposta


# ==============================================================================
# SALDOS E PAGAMENTOS
# ==============================================================================
@permission_required("leite.view_pagamentoprodutor", raise_exception=True)
def saldos(request):
    """Relatório de totais devidos: leite recebido - pagamentos = saldo a pagar."""
    linhas = servicos.saldos_produtores()
    totais = {
        "litros": sum((l["litros"] for l in linhas), Decimal("0")),
        "valor": sum((l["valor"] for l in linhas), Decimal("0")),
        "pago": sum((l["pago"] for l in linhas), Decimal("0")),
        "saldo": sum((l["saldo"] for l in linhas), Decimal("0")),
    }
    grafico = {
        "rotulos": [l["produtor"].nome for l in linhas if l["saldo"] > 0][:15],
        "series": [{"rotulo": "Saldo a pagar (R$)", "dados": [float(l["saldo"]) for l in linhas if l["saldo"] > 0][:15]}],
    }
    return render(request, "leite/saldos.html", {"linhas": linhas, "totais": totais, "grafico": grafico})


@permission_required("leite.add_pagamentoprodutor", raise_exception=True)
def pagamento_novo(request, produtor_pk):
    produtor = get_object_or_404(Produtor, pk=produtor_pk)
    saldo = servicos.saldo_do_produtor(produtor)
    hoje = timezone.localdate()
    inicial = {
        "data": hoje,
        "valor": saldo["saldo"] if saldo and saldo["saldo"] > 0 else None,
        "forma_pagamento": "PIX" if produtor.chave_pix else "DINHEIRO",
    }
    form = PagamentoForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        try:
            pagamento = servicos.registrar_pagamento(
                produtor=produtor, valor=dados["valor"], data=dados["data"],
                forma_pagamento=dados["forma_pagamento"], usuario=request.user,
                valor_dinheiro=dados.get("valor_dinheiro"), valor_pix=dados.get("valor_pix"),
                periodo_inicio=dados.get("periodo_inicio"), periodo_fim=dados.get("periodo_fim"),
                observacao=dados.get("observacao", ""),
            )
        except ValidationError as erro:
            _mostrar_erro(request, erro)
        else:
            messages.success(request, f"Pagamento de {moeda(pagamento.valor)} registrado e lançado no caixa.")
            if saldo and pagamento.valor > saldo["saldo"]:
                messages.warning(request, "O valor pago é maior que o saldo: a diferença fica como adiantamento.")
            return redirect("leite:produtor_detalhe", pk=produtor.pk)
    return render(request, "leite/pagamento_form.html", {"form": form, "produtor": produtor, "saldo": saldo})


@permission_required("leite.view_pagamentoprodutor", raise_exception=True)
def pagamentos_lista(request):
    produtor = _produtor_da_url(request)
    inicio = ler_data(request.GET.get("inicio"))
    fim = ler_data(request.GET.get("fim"))
    pagamentos = PagamentoProdutor.objects.select_related("produtor", "usuario")
    if produtor:
        pagamentos = pagamentos.filter(produtor=produtor)
    if inicio:
        pagamentos = pagamentos.filter(data__gte=inicio)
    if fim:
        pagamentos = pagamentos.filter(data__lte=fim)
    total = pagamentos.filter(estornado=False).aggregate(t=Sum("valor"))["t"] or Decimal("0")
    return render(request, "leite/pagamentos_lista.html", {
        "pagina": paginar(request, pagamentos),
        "produtores": Produtor.objects.all(),
        "produtor": produtor, "inicio": inicio, "fim": fim, "total": total,
    })


@require_http_methods(["GET", "POST"])
@permission_required("leite.estornar_pagamento", raise_exception=True)
def pagamento_estornar(request, pk):
    pagamento = get_object_or_404(PagamentoProdutor.objects.select_related("produtor"), pk=pk)
    form = EstornoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            servicos.estornar_pagamento(pagamento, motivo=form.cleaned_data["motivo"], usuario=request.user)
        except ValidationError as erro:
            _mostrar_erro(request, erro)
        else:
            messages.success(request, "Pagamento estornado. A saída no caixa também foi estornada.")
        return redirect("leite:pagamentos")
    return render(request, "leite/pagamento_estornar.html", {"form": form, "pagamento": pagamento})


# ==============================================================================
# COLETA OFFLINE (PWA): API usada pela fila do celular + service worker + manifest
# ==============================================================================
def _estado_coleta(request):
    """Tudo que a página do coletor precisa para funcionar sem internet (sem preços!)."""
    return {
        "usuario": request.user.username,
        "hoje": timezone.localdate().isoformat(),
        "gerado_em": timezone.now().isoformat(),
        "dias_permitidos": settings.COLETA_OFFLINE_DIAS,
        "produtores": [
            {"id": p.pk, "nome": p.nome, "propriedade": p.apelido_propriedade}
            for p in Produtor.objects.filter(ativo=True).order_by("nome")
        ],
        "lancados_hoje": [
            {"produtor": c.produtor_id, "nome": c.produtor.nome, "litros": str(c.litros), "forma": c.forma,
             "hora": timezone.localtime(c.criado_em).strftime("%H:%M")}
            for c in servicos.coletas_de_hoje().order_by("-criado_em")
        ],
    }


def _json_sem_acesso(request):
    """Resposta em JSON (e não redirecionamento) quando o celular não está logado ou não tem permissão."""
    if not request.user.is_authenticated:
        return JsonResponse({"autenticado": False, "erro": "Entre no sistema para enviar os lançamentos."}, status=401)
    if not request.user.has_perm("leite.registrar_coleta_diaria"):
        return JsonResponse({"autenticado": True, "erro": "Seu usuário não pode lançar leite."}, status=403)
    return None


@login_not_required  # a própria view responde 401 em JSON
@never_cache
@require_GET
def api_coleta_estado(request):
    """Dados que o celular guarda para trabalhar offline: produtores, usuário, token CSRF e o que já foi lançado hoje."""
    negado = _json_sem_acesso(request)
    if negado:
        return negado
    estado = _estado_coleta(request)
    estado.update({"autenticado": True, "csrf": get_token(request)})
    return JsonResponse(estado)


@login_not_required  # a própria view responde 401 em JSON; o CSRF continua obrigatório
@never_cache
@require_POST
def api_coleta_sincronizar(request):
    """Recebe a fila de lançamentos feitos offline e devolve o resultado de cada um."""
    negado = _json_sem_acesso(request)
    if negado:
        return negado
    try:
        dados = json.loads(request.body.decode("utf-8"))
        itens = dados["itens"]
        if not isinstance(itens, list):
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return JsonResponse({"erro": "Formato inválido."}, status=400)
    if len(itens) > settings.COLETA_OFFLINE_MAX_ITENS:
        return JsonResponse({"erro": f"Envie no máximo {settings.COLETA_OFFLINE_MAX_ITENS} lançamentos por vez."}, status=400)
    resultados = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        status, mensagem = servicos.sincronizar_item(item, request.user)
        resultados.append({"codigo": str(item.get("codigo", ""))[:40], "status": status, "mensagem": mensagem})
    return JsonResponse({"resultados": resultados})


@login_not_required
@require_GET
def service_worker(request):
    """O service worker precisa ser servido de dentro de /leite/coleta-diaria/ para controlar essa página."""
    resposta = render(request, "pwa/sw.js", {"versao": VERSAO_PWA}, content_type="application/javascript")
    resposta["Cache-Control"] = "no-cache"
    return resposta


@login_not_required
@require_GET
def manifest(request):
    """Manifesto do app: nome, ícone e cores do atalho na tela inicial do celular."""
    return render(request, "pwa/manifest.webmanifest", content_type="application/manifest+json")
