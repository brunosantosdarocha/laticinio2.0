"""
financeiro/views.py
===================
Telas do caixa:
- novo lançamento (entrada ou saída);
- extrato com filtros, totais e gráficos (substitui "Informações Gerais" do Streamlit);
- estorno (no lugar de apagar);
- categorias.
"""

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.utils import paginar, primeiro_dia_mes, ultimo_dia_mes

from . import servicos
from .forms import CategoriaForm, EstornoForm, FiltroExtratoForm, LancamentoForm
from .models import Categoria, Lancamento, TipoLancamento

TIPOS_URL = {"entrada": TipoLancamento.ENTRADA, "saida": TipoLancamento.SAIDA}


@permission_required("financeiro.add_lancamento", raise_exception=True)
def lancamento_novo(request, tipo):
    """Cadastro de entrada (/financeiro/novo/entrada/) ou saída (/financeiro/novo/saida/)."""
    if tipo not in TIPOS_URL:
        raise Http404
    tipo_banco = TIPOS_URL[tipo]
    form = LancamentoForm(request.POST or None, tipo=tipo_banco, initial={"data": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            servicos.criar_lancamento(tipo=tipo_banco, usuario=request.user, **form.cleaned_data)
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
        else:
            messages.success(request, f"{'Entrada' if tipo == 'entrada' else 'Saída'} salva com sucesso!")
            if "salvar_e_novo" in request.POST:
                return redirect("financeiro:lancamento_novo", tipo=tipo)
            return redirect("financeiro:extrato")
    ultimos = Lancamento.objects.filter(tipo=tipo_banco).select_related("categoria")[:8]
    return render(request, "financeiro/lancamento_form.html", {
        "form": form, "tipo": tipo, "eh_entrada": tipo == "entrada", "ultimos": ultimos,
    })


@permission_required("financeiro.view_lancamento", raise_exception=True)
def extrato(request):
    """Extrato com filtros. Os totais e gráficos ignoram os lançamentos estornados."""
    hoje = timezone.localdate()
    dados_get = request.GET.copy()
    if not dados_get.get("inicio") and not dados_get.get("fim"):
        dados_get["inicio"] = primeiro_dia_mes(hoje).isoformat()
        dados_get["fim"] = ultimo_dia_mes(hoje).isoformat()
    form = FiltroExtratoForm(dados_get)
    consulta = Lancamento.objects.select_related("categoria", "usuario")
    if form.is_valid():
        f = form.cleaned_data
        if f["inicio"]:
            consulta = consulta.filter(data__gte=f["inicio"])
        if f["fim"]:
            consulta = consulta.filter(data__lte=f["fim"])
        if f["tipo"]:
            consulta = consulta.filter(tipo=f["tipo"])
        if f["categoria"]:
            consulta = consulta.filter(categoria=f["categoria"])
        if f["q"]:
            consulta = consulta.filter(descricao__icontains=f["q"])
        mostrar_estornados = f["estornados"]
    else:
        mostrar_estornados = False

    validos = consulta.filter(estornado=False)
    totais = servicos.totais(validos)
    por_entrada = servicos.somas_por_categoria(validos, TipoLancamento.ENTRADA)
    por_saida = servicos.somas_por_categoria(validos, TipoLancamento.SAIDA)
    lista = consulta if mostrar_estornados else validos
    return render(request, "financeiro/extrato.html", {
        "form": form,
        "pagina": paginar(request, lista, 25),
        "totais": totais,
        "por_entrada": por_entrada,
        "por_saida": por_saida,
        "grafico_entradas": {"rotulos": [n for n, _ in por_entrada],
                             "series": [{"rotulo": "Entradas (R$)", "dados": [float(v) for _, v in por_entrada]}]},
        "grafico_saidas": {"rotulos": [n for n, _ in por_saida],
                           "series": [{"rotulo": "Saídas (R$)", "dados": [float(v) for _, v in por_saida]}]},
    })


@require_http_methods(["GET", "POST"])
@permission_required("financeiro.estornar_lancamento", raise_exception=True)
def lancamento_estornar(request, pk):
    lancamento = get_object_or_404(Lancamento.objects.select_related("categoria"), pk=pk)
    form = EstornoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            servicos.estornar_lancamento(lancamento, motivo=form.cleaned_data["motivo"], usuario=request.user)
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
        else:
            messages.success(request, "Lançamento estornado. Ele continua no histórico, mas saiu dos totais.")
        return redirect("financeiro:extrato")
    return render(request, "financeiro/lancamento_estornar.html", {"form": form, "lancamento": lancamento})


@permission_required("financeiro.view_categoria", raise_exception=True)
def categorias_lista(request):
    return render(request, "financeiro/categorias_lista.html", {
        "entradas": Categoria.objects.filter(tipo=TipoLancamento.ENTRADA),
        "saidas": Categoria.objects.filter(tipo=TipoLancamento.SAIDA),
    })


@permission_required("financeiro.add_categoria", raise_exception=True)
def categoria_criar(request):
    form = CategoriaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Categoria criada.")
        return redirect("financeiro:categorias")
    return render(request, "financeiro/categoria_form.html", {"form": form, "titulo": "Nova categoria"})


@permission_required("financeiro.change_categoria", raise_exception=True)
def categoria_editar(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if categoria.sistema:
        messages.warning(request, "Esta categoria é usada automaticamente pelo sistema e não pode ser alterada.")
        return redirect("financeiro:categorias")
    form = CategoriaForm(request.POST or None, instance=categoria)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Categoria atualizada.")
        return redirect("financeiro:categorias")
    return render(request, "financeiro/categoria_form.html", {"form": form, "titulo": f"Editar: {categoria.nome}"})
