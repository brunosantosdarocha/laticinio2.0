"""
Comando: python manage.py importar_streamlit caminho/financeiro.db [--simular]

Traz os dados do sistema antigo em Streamlit (crudf.py) para o Django:
- tabela "leite": nomes viram Produtores; linhas com data viram Coletas
  (litros 0 continuam sendo FALTA; se houver duas linhas no mesmo dia, vale a última);
- tabela "financ": cada coluna entrada1..10 / saida1..10 com valor > 0 vira um
  Lançamento na categoria correspondente, com a observação como descrição.

Pode ser rodado mais de uma vez: coletas já existentes (mesmo produtor e dia) são atualizadas,
e lançamentos idênticos (mesmo tipo, categoria, valor, data e descrição) não são duplicados.
Use --simular para ver o que seria importado sem gravar nada.
"""

import datetime
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from financeiro.models import Categoria, Lancamento, TipoLancamento
from leite.models import Coleta, FormaColeta, Produtor

# Mesmos dicionários do crudf.py (coluna do banco antigo -> nome da categoria)
SAIDAS = {
    "saida1": "Combustivel / Gasolina", "saida2": "Combustivel / Alchol", "saida3": "Combustivel / Diesel",
    "saida4": "Mercado / alimentação", "saida5": "Saúde / Farmácia", "saida6": "Lazer / Viagens",
    "saida7": "Educação", "saida8": "Vestuário", "saida9": "Adiantamentos / (Flavio/Bruno/Maciel)",
    "saida10": "Outros Gastos",
}
ENTRADAS = {
    "entrada1": "Suinos", "entrada2": "Frango", "entrada3": "Queijos", "entrada4": "Soro",
    "entrada5": "Produção semanal", "entrada6": "Reembolsos", "entrada7": "Abono Salarial",
    "entrada8": "Prêmios", "entrada9": "Doações / Presentes", "entrada10": "Outras Receitas",
}


class Simulacao(Exception):
    """Usada para desfazer tudo no modo --simular."""


def _decimal(valor, casas="0.01"):
    try:
        return Decimal(str(valor or 0)).quantize(Decimal(casas))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _data(texto):
    try:
        return datetime.date.fromisoformat(str(texto)[:10])
    except (TypeError, ValueError):
        return None


class Command(BaseCommand):
    help = "Importa produtores, leite e financeiro do banco antigo do Streamlit (financeiro.db)."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="Caminho do financeiro.db do Streamlit")
        parser.add_argument("--simular", action="store_true", help="Mostra o resultado sem gravar")

    def handle(self, *args, **options):
        caminho = Path(options["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        antigo = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)  # somente leitura
        antigo.row_factory = sqlite3.Row
        tabelas = {r[0] for r in antigo.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "leite" not in tabelas and "financ" not in tabelas:
            raise CommandError("Este arquivo não tem as tabelas 'leite' e 'financ' do sistema antigo.")

        resumo = {"produtores": 0, "coletas_novas": 0, "coletas_atualizadas": 0, "lancamentos": 0, "ignorados": 0}
        try:
            with transaction.atomic():
                if "leite" in tabelas:
                    self._importar_leite(antigo, resumo)
                if "financ" in tabelas:
                    self._importar_financeiro(antigo, resumo)
                if options["simular"]:
                    raise Simulacao
        except Simulacao:
            self.stdout.write(self.style.WARNING("SIMULAÇÃO: nada foi gravado."))
        finally:
            antigo.close()

        for chave, valor in resumo.items():
            self.stdout.write(f"  {chave.replace('_', ' ')}: {valor}")
        self.stdout.write(self.style.SUCCESS("Importação concluída."))

    def _produtor(self, nome, cache, resumo):
        nome = " ".join((nome or "").split())
        if not nome:
            return None
        chave = nome.lower()
        if chave not in cache:
            produtor = Produtor.objects.filter(nome__iexact=nome).first()
            if produtor is None:
                produtor = Produtor.objects.create(nome=nome)
                resumo["produtores"] += 1
            cache[chave] = produtor
        return cache[chave]

    def _importar_leite(self, antigo, resumo):
        cache = {}
        linhas = antigo.execute(
            "SELECT nome_produtor, data_recebimento, quantidade_leite, valor_leite FROM leite ORDER BY id_recebimento"
        )
        for linha in linhas:
            produtor = self._produtor(linha["nome_produtor"], cache, resumo)
            data = _data(linha["data_recebimento"])
            if produtor is None or data is None or linha["quantidade_leite"] is None:
                continue  # linha de "cadastro" (só o nome) ou incompleta
            litros = _decimal(linha["quantidade_leite"], "0.1")
            preco = _decimal(linha["valor_leite"])
            if litros < 0:
                resumo["ignorados"] += 1
                continue
            _, criada = Coleta.objects.update_or_create(
                produtor=produtor, data=data,
                defaults={"litros": litros, "preco_litro": preco, "forma": FormaColeta.ESCRITORIO},
            )
            resumo["coletas_novas" if criada else "coletas_atualizadas"] += 1
        # O preço padrão de cada produtor passa a ser o último preço usado no sistema antigo.
        for produtor in cache.values():
            ultima = produtor.coletas.exclude(preco_litro=0).order_by("-data").first()
            if ultima:
                produtor.preco_litro = ultima.preco_litro
                produtor.save(update_fields=["preco_litro"])

    def _importar_financeiro(self, antigo, resumo):
        colunas = {r[1] for r in antigo.execute("PRAGMA table_info(financ)")}
        mapas = [(TipoLancamento.ENTRADA, ENTRADAS, "observacao_entrada"),
                 (TipoLancamento.SAIDA, SAIDAS, "observacao_saida")]
        for linha in antigo.execute("SELECT * FROM financ ORDER BY id_gastos"):
            data = _data(linha["data"])
            if data is None:
                resumo["ignorados"] += 1
                continue
            for tipo, mapa, coluna_obs in mapas:
                for coluna, nome_categoria in mapa.items():
                    if coluna not in colunas:
                        continue
                    valor = _decimal(linha[coluna])
                    if valor <= 0:
                        continue
                    categoria, _ = Categoria.objects.get_or_create(nome=nome_categoria, tipo=tipo)
                    descricao = (linha[coluna_obs] if coluna_obs in colunas else "") or ""
                    descricao = str(descricao).strip()[:200]
                    existe = Lancamento.objects.filter(
                        tipo=tipo, categoria=categoria, valor=valor, data=data, descricao=descricao
                    ).exists()
                    if existe:
                        resumo["ignorados"] += 1
                        continue
                    Lancamento.objects.create(tipo=tipo, categoria=categoria, valor=valor, data=data, descricao=descricao)
                    resumo["lancamentos"] += 1
