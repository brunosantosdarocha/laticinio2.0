"""
leite/servicos.py
=================
Regras de negócio do leite. As views chamam estas funções; aqui fica a "inteligência".

Principais funções:
- registrar_coleta_diaria ... página do coletor (só insere, nunca altera)
- salvar_calendario ......... grade mensal do escritório (cria, altera e remove dias)
- atualizar_preco_em_massa .. corrige o preço de vários dias de uma vez
- resumo_periodo ............ dados do recibo (litros, valores, faltas)
- saldos_produtores ......... quanto cada produtor tem a receber
- registrar_pagamento / estornar_pagamento
"""

import calendar
import datetime
import logging
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from core.escolhas import FormaPagamento
from core.utils import dinheiro
from financeiro import servicos as financeiro_servicos
from financeiro.models import TipoLancamento

from .models import Coleta, FormaColeta, PagamentoProdutor, Produtor

logger = logging.getLogger("laticinio")

LITROS_MAXIMO_DIA = Decimal("99999.9")
UM_DECIMO = Decimal("0.1")


def _litros(valor):
    """Converte para Decimal com 1 casa e confere os limites."""
    try:
        litros = Decimal(str(valor)).quantize(UM_DECIMO)
    except (InvalidOperation, ValueError):
        raise ValidationError("Quantidade de litros inválida.")
    if litros < 0:
        raise ValidationError("A quantidade de litros não pode ser negativa.")
    if litros > LITROS_MAXIMO_DIA:
        raise ValidationError("Quantidade de litros muito alta. Confira o número digitado.")
    return litros


# ------------------------------------------------------------------------------
# Produtores
# ------------------------------------------------------------------------------
@transaction.atomic
def excluir_produtor(produtor):
    """Apaga o produtor e TODO o histórico de leite dele (igual ao sistema antigo).

    Só é permitido se não houver pagamentos registrados: pagamento é histórico
    financeiro e não pode sumir. Nesse caso, use "inativar".
    """
    if produtor.pagamentos.exists():
        raise ValidationError(
            "Este produtor tem pagamentos registrados e não pode ser apagado. Marque-o como inativo."
        )
    nome = produtor.nome
    quantidade, _ = produtor.coletas.all().delete()
    produtor.delete()
    logger.info("Produtor '%s' apagado com %s lançamentos de leite.", nome, quantidade)
    return quantidade


# ------------------------------------------------------------------------------
# Coleta diária (página do coletor)
# ------------------------------------------------------------------------------
def validar_data_coleta(data):
    """Data aceita na coleta: de hoje até COLETA_OFFLINE_DIAS dias atrás (nunca no futuro)."""
    hoje = timezone.localdate()
    if data > hoje:
        raise ValidationError("A data do lançamento está no futuro. Confira a data do celular.")
    limite = hoje - datetime.timedelta(days=settings.COLETA_OFFLINE_DIAS)
    if data < limite:
        raise ValidationError(
            f"Lançamento de {data:%d/%m/%Y} é antigo demais (mais de {settings.COLETA_OFFLINE_DIAS} dias). "
            "Avise o escritório para lançar pelo calendário."
        )


def registrar_coleta_diaria(*, produtor, litros, forma, usuario, data=None, codigo=None):
    """Lança o leite de um produtor pela página do coletor.

    Regras:
    - pelo formulário normal a data é sempre a de hoje (vem do servidor);
    - pela fila offline a data vem do celular, mas só vale de hoje até N dias atrás;
    - o preço vem do cadastro do produtor (o coletor nem vê o preço);
    - só INSERE: se o produtor já tem lançamento no dia, não altera — avisa para
      o escritório corrigir pelo calendário.
    """
    data = data or timezone.localdate()
    validar_data_coleta(data)
    if not produtor.ativo:
        raise ValidationError("Este produtor está inativo.")
    if forma not in (FormaColeta.COLETADO, FormaColeta.ENTREGUE):
        raise ValidationError("Escolha se o leite foi coletado ou entregue.")
    litros = _litros(litros)
    if litros <= 0:
        raise ValidationError("Informe a quantidade de litros (maior que zero).")

    quando = "hoje" if data == timezone.localdate() else f"em {data:%d/%m/%Y}"
    existente = Coleta.objects.filter(produtor=produtor, data=data).first()
    if existente:
        litros_txt = f"{existente.litros}".replace(".", ",")
        raise ValidationError(
            f"{produtor.nome} já tem {litros_txt} L lançados {quando}. Para corrigir, peça ao escritório."
        )
    try:
        with transaction.atomic():
            coleta = Coleta.objects.create(
                produtor=produtor, data=data, litros=litros, preco_litro=produtor.preco_litro,
                forma=forma, usuario=usuario, codigo_offline=codigo,
            )
    except IntegrityError:
        # Dois celulares lançando o mesmo produtor ao mesmo tempo.
        raise ValidationError(f"{produtor.nome} acabou de ser lançado por outra pessoa {quando}.")
    logger.info("Coleta: %s - %s L (%s) em %s por %s", produtor, litros, forma, data, usuario)
    return coleta


def sincronizar_item(item, usuario):
    """Grava UM lançamento vindo da fila offline do celular.

    item = {"codigo": uuid, "produtor": id, "forma": "COLETADO"/"ENTREGUE", "litros": "12.5", "data": "2026-11-15"}
    Devolve (status, mensagem):
      "ok"       -> gravado agora
      "repetido" -> esse código já tinha sido recebido antes (o celular pode apagar da fila)
      "erro"     -> recusado por uma regra (o celular mostra ao coletor e não tenta de novo)
    """
    try:
        codigo = uuid.UUID(str(item.get("codigo", "")))
    except ValueError:
        return "erro", "Lançamento sem código válido."
    if Coleta.objects.filter(codigo_offline=codigo).exists():
        return "repetido", "Já tinha sido recebido."
    try:
        data = datetime.date.fromisoformat(str(item.get("data", ""))[:10])
    except ValueError:
        return "erro", "Data inválida."
    produtor_id = str(item.get("produtor", ""))
    produtor = Produtor.objects.filter(pk=int(produtor_id)).first() if produtor_id.isdigit() else None
    if produtor is None:
        return "erro", "Produtor não encontrado. Ele pode ter sido apagado."
    try:
        coleta = registrar_coleta_diaria(
            produtor=produtor, litros=item.get("litros"), forma=item.get("forma"),
            usuario=usuario, data=data, codigo=codigo,
        )
    except ValidationError as erro:
        # Corrida: o mesmo código chegou por duas conexões ao mesmo tempo.
        if Coleta.objects.filter(codigo_offline=codigo).exists():
            return "repetido", "Já tinha sido recebido."
        return "erro", " ".join(erro.messages)
    return "ok", f"{coleta.produtor.nome}: {str(coleta.litros).replace('.', ',')} L em {coleta.data:%d/%m/%Y}."


def coletas_de_hoje():
    return Coleta.objects.filter(data=timezone.localdate()).select_related("produtor", "usuario")


def produtores_sem_coleta(data=None):
    """Produtores ativos que ainda não têm lançamento na data."""
    data = data or timezone.localdate()
    return Produtor.objects.filter(ativo=True).exclude(coletas__data=data)


# ------------------------------------------------------------------------------
# Calendário mensal (escritório)
# ------------------------------------------------------------------------------
def dias_do_mes(ano, mes):
    """Semanas do mês no formato do calendar.monthcalendar (0 = dia fora do mês)."""
    return calendar.monthcalendar(ano, mes)


def coletas_do_mes(produtor, ano, mes):
    """Dicionário {dia: Coleta} do produtor no mês."""
    consulta = Coleta.objects.filter(produtor=produtor, data__year=ano, data__month=mes)
    return {coleta.data.day: coleta for coleta in consulta}


@transaction.atomic
def salvar_calendario(*, produtor, ano, mes, valores, faltas, preco_padrao, usuario):
    """Grava a grade do calendário de uma vez só.

    valores: {dia: texto digitado}  (vazio = sem lançamento)
    faltas:  conjunto de dias marcados como "Falta" (gravados com 0 litros)

    - dia novo com litros -> cria com o preço padrão informado;
    - dia existente com litros diferentes -> altera só os litros (mantém o preço já usado);
    - dia existente que ficou vazio -> remove o lançamento;
    Devolve um dicionário com as contagens (criados, alterados, removidos).
    """
    preco_padrao = dinheiro(preco_padrao)
    if preco_padrao < 0:
        raise ValidationError("O preço padrão não pode ser negativo.")
    ultimo = calendar.monthrange(ano, mes)[1]
    existentes = {
        c.data.day: c
        for c in Coleta.objects.select_for_update().filter(produtor=produtor, data__year=ano, data__month=mes)
    }
    contagem = {"criados": 0, "alterados": 0, "removidos": 0}
    erros = []

    for dia in range(1, ultimo + 1):
        texto = (valores.get(dia) or "").strip().replace(",", ".")
        if dia in faltas:
            litros = Decimal("0.0")
        elif texto == "":
            litros = None
        else:
            try:
                litros = _litros(texto)
            except ValidationError as erro:
                erros.append(f"Dia {dia}: {erro.messages[0]}")
                continue

        atual = existentes.get(dia)
        if litros is None:
            if atual:
                atual.delete()
                contagem["removidos"] += 1
        elif atual is None:
            Coleta.objects.create(
                produtor=produtor, data=datetime.date(ano, mes, dia), litros=litros,
                preco_litro=preco_padrao, forma=FormaColeta.ESCRITORIO, usuario=usuario,
            )
            contagem["criados"] += 1
        elif atual.litros != litros:
            atual.litros = litros
            atual.usuario = usuario
            atual.save(update_fields=["litros", "usuario", "atualizado_em"])
            contagem["alterados"] += 1

    if erros:
        # Desfaz tudo (transaction.atomic) para não gravar a grade pela metade.
        raise ValidationError(erros)
    return contagem


@transaction.atomic
def editar_coleta(coleta, *, litros, preco_litro, forma, usuario):
    coleta.litros = _litros(litros)
    preco = dinheiro(preco_litro)
    if preco < 0:
        raise ValidationError("O preço não pode ser negativo.")
    coleta.preco_litro = preco
    coleta.forma = forma
    coleta.usuario = usuario
    coleta.save()
    return coleta


def atualizar_preco_em_massa(*, produtor, inicio, fim, preco_atual, novo_preco):
    """Troca o preço do litro de vários lançamentos de uma vez.

    - produtor=None -> todos os produtores;
    - preco_atual=None -> qualquer preço; senão só os que estão exatamente com esse preço.
    Devolve quantos registros foram alterados.
    """
    if inicio > fim:
        raise ValidationError("A data de início não pode ser maior que a data final.")
    novo_preco = dinheiro(novo_preco)
    if novo_preco < 0:
        raise ValidationError("O novo preço não pode ser negativo.")
    consulta = Coleta.objects.filter(data__gte=inicio, data__lte=fim)
    if produtor is not None:
        consulta = consulta.filter(produtor=produtor)
    if preco_atual is not None:
        consulta = consulta.filter(preco_litro=dinheiro(preco_atual))
    quantidade = consulta.update(preco_litro=novo_preco, atualizado_em=timezone.now())
    logger.info("Preço em massa: %s registros -> R$ %s (%s a %s)", quantidade, novo_preco, inicio, fim)
    return quantidade


# ------------------------------------------------------------------------------
# Recibo e saldos
# ------------------------------------------------------------------------------
def resumo_periodo(produtor, inicio, fim):
    """Tudo que o recibo precisa: lista de dias, totais e quantidade de faltas."""
    coletas = list(
        Coleta.objects.filter(produtor=produtor, data__gte=inicio, data__lte=fim).order_by("data")
    )
    total_litros = sum((c.litros for c in coletas), Decimal("0"))
    total_valor = sum((c.valor_total for c in coletas), Decimal("0"))
    pagamentos = list(
        PagamentoProdutor.objects.filter(
            produtor=produtor, estornado=False, data__gte=inicio, data__lte=fim
        )
    )
    total_pago = sum((p.valor for p in pagamentos), Decimal("0"))
    return {
        "coletas": coletas,
        "total_litros": total_litros,
        "total_valor": dinheiro(total_valor),
        "faltas": sum(1 for c in coletas if c.falta),
        "dias_entregues": sum(1 for c in coletas if not c.falta),
        "media_litros": (total_litros / len(coletas)).quantize(UM_DECIMO) if coletas else Decimal("0"),
        "pagamentos": pagamentos,
        "total_pago": total_pago,
    }


def texto_whatsapp_recibo(produtor, inicio, fim, resumo, nome_empresa):
    """Mensagem curta do recibo para enviar ao produtor pelo WhatsApp."""
    linhas = [
        f"*{nome_empresa}* - Comprovante de leite",
        f"Produtor: {produtor.nome}",
        f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}",
        f"Total: {resumo['total_litros']:.1f} L".replace(".", ","),
        f"Valor: R$ {resumo['total_valor']:.2f}".replace(".", ","),
    ]
    if resumo["faltas"]:
        linhas.append(f"Faltas no período: {resumo['faltas']} dia(s)")
    return "\n".join(linhas)


def saldos_produtores(apenas_com_movimento=True):
    """Para cada produtor: litros, valor total do leite, total pago e saldo a receber.

    O valor do leite é somado linha a linha em Python (litros x preço arredondado),
    exatamente como no recibo, para não haver diferença de centavos.
    """
    valores = {}
    for produtor_id, litros, preco in Coleta.objects.values_list("produtor_id", "litros", "preco_litro"):
        item = valores.setdefault(produtor_id, {"litros": Decimal("0"), "valor": Decimal("0")})
        item["litros"] += litros
        item["valor"] += dinheiro(litros * preco)
    pagos = dict(
        PagamentoProdutor.objects.filter(estornado=False)
        .values("produtor_id").annotate(t=Sum("valor")).values_list("produtor_id", "t")
    )
    resultado = []
    for produtor in Produtor.objects.all():
        item = valores.get(produtor.id, {"litros": Decimal("0"), "valor": Decimal("0")})
        pago = pagos.get(produtor.id) or Decimal("0")
        if apenas_com_movimento and not item["litros"] and not pago:
            continue
        resultado.append({
            "produtor": produtor,
            "litros": item["litros"],
            "valor": item["valor"],
            "pago": pago,
            "saldo": item["valor"] - pago,
        })
    resultado.sort(key=lambda linha: linha["saldo"], reverse=True)
    return resultado


def saldo_do_produtor(produtor):
    for linha in saldos_produtores(apenas_com_movimento=False):
        if linha["produtor"].pk == produtor.pk:
            return linha
    return None


# ------------------------------------------------------------------------------
# Pagamentos a produtores
# ------------------------------------------------------------------------------
@transaction.atomic
def registrar_pagamento(*, produtor, valor, data, forma_pagamento, usuario,
                        valor_dinheiro=0, valor_pix=0, periodo_inicio=None, periodo_fim=None, observacao=""):
    """Registra o pagamento e cria automaticamente a saída no caixa."""
    valor = dinheiro(valor)
    if valor <= 0:
        raise ValidationError("Informe um valor maior que zero.")
    valor_dinheiro = dinheiro(valor_dinheiro or 0)
    valor_pix = dinheiro(valor_pix or 0)
    if forma_pagamento == FormaPagamento.MISTO:
        if valor_dinheiro <= 0 or valor_pix <= 0 or valor_dinheiro + valor_pix != valor:
            raise ValidationError("No pagamento misto, dinheiro + Pix precisa fechar exatamente o valor pago.")
    else:
        valor_dinheiro = valor if forma_pagamento == FormaPagamento.DINHEIRO else Decimal("0")
        valor_pix = valor if forma_pagamento == FormaPagamento.PIX else Decimal("0")
    if periodo_inicio and periodo_fim and periodo_inicio > periodo_fim:
        raise ValidationError("O início do período não pode ser depois do fim.")

    descricao = f"Pagamento de leite - {produtor.nome}"
    if periodo_inicio and periodo_fim:
        descricao += f" ({periodo_inicio:%d/%m} a {periodo_fim:%d/%m/%Y})"
    lancamento = financeiro_servicos.criar_lancamento(
        tipo=TipoLancamento.SAIDA,
        categoria=financeiro_servicos.categoria_pagamento_produtor(),
        valor=valor, data=data, descricao=descricao[:200],
        forma_pagamento=forma_pagamento, usuario=usuario,
    )
    pagamento = PagamentoProdutor.objects.create(
        produtor=produtor, data=data, valor=valor, forma_pagamento=forma_pagamento,
        valor_dinheiro=valor_dinheiro, valor_pix=valor_pix,
        periodo_inicio=periodo_inicio, periodo_fim=periodo_fim,
        observacao=observacao, lancamento=lancamento, usuario=usuario,
    )
    logger.info("Pagamento ao produtor %s: R$ %s por %s", produtor, valor, usuario)
    return pagamento


@transaction.atomic
def estornar_pagamento(pagamento, *, motivo, usuario):
    """Estorna o pagamento e a saída correspondente do caixa (os dois juntos)."""
    pagamento = PagamentoProdutor.objects.select_for_update().get(pk=pagamento.pk)
    if pagamento.estornado:
        raise ValidationError("Este pagamento já foi estornado.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo do estorno.")
    pagamento.estornado = True
    pagamento.estornado_em = timezone.now()
    pagamento.motivo_estorno = motivo[:200]
    pagamento.save(update_fields=["estornado", "estornado_em", "motivo_estorno"])
    if pagamento.lancamento_id and not pagamento.lancamento.estornado:
        financeiro_servicos.estornar_lancamento(
            pagamento.lancamento, motivo=f"Estorno do pagamento: {motivo}", usuario=usuario,
            permitir_vinculado=True,
        )
    return pagamento


# ------------------------------------------------------------------------------
# Indicadores (dashboard)
# ------------------------------------------------------------------------------
def litros_periodo(inicio, fim):
    return Coleta.objects.filter(data__gte=inicio, data__lte=fim).aggregate(t=Sum("litros"))["t"] or Decimal("0")
