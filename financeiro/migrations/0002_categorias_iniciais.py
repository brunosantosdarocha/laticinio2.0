"""
Migração de dados: cria as categorias que existiam no sistema Streamlit
(DIC_ENTRADAS e DIC_SAIDAS do crudf.py) + a categoria automática "Pagamento a produtores".
"""

from django.db import migrations

ENTRADAS = [
    "Suinos", "Frango", "Queijos", "Soro", "Produção semanal",
    "Reembolsos", "Abono Salarial", "Prêmios", "Doações / Presentes", "Outras Receitas",
]
SAIDAS = [
    "Combustivel / Gasolina", "Combustivel / Alchol", "Combustivel / Diesel", "Mercado / alimentação",
    "Saúde / Farmácia", "Lazer / Viagens", "Educação", "Vestuário",
    "Adiantamentos / (Flavio/Bruno/Maciel)", "Outros Gastos",
]


def criar(apps, schema_editor):
    Categoria = apps.get_model("financeiro", "Categoria")
    for nome in ENTRADAS:
        Categoria.objects.get_or_create(nome=nome, tipo="ENTRADA")
    for nome in SAIDAS:
        Categoria.objects.get_or_create(nome=nome, tipo="SAIDA")
    Categoria.objects.get_or_create(nome="Pagamento a produtores", tipo="SAIDA", defaults={"sistema": True})


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0001_initial")]
    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
