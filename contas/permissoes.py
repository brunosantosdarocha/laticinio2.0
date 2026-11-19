"""
contas/permissoes.py
====================
Lista OFICIAL de permissões que aparecem na tela "Níveis de acesso".

Cada módulo tem ações: ver / criar / editar / excluir + ações especiais.
A tela só grava permissões que estão nesta lista (função codigos_permitidos),
então ninguém consegue "inventar" permissões enviando um formulário adulterado.

NIVEIS_PADRAO define os grupos criados pelo comando configurar_grupos.
"""

# (rótulo do módulo, app, model, {ação: codename})
MODULOS = [
    {
        "nome": "Coleta diária (página do coletor)",
        "app": "leite",
        "acoes": {"especial": [("registrar_coleta_diaria", "Lançar leite de hoje")]},
    },
    {
        "nome": "Produtores",
        "app": "leite",
        "acoes": {
            "ver": "view_produtor", "criar": "add_produtor",
            "editar": "change_produtor", "excluir": "delete_produtor",
        },
    },
    {
        "nome": "Calendário do leite",
        "app": "leite",
        "acoes": {
            "ver": "view_coleta", "criar": "add_coleta", "editar": "change_coleta", "excluir": "delete_coleta",
            "especial": [("alterar_preco_massa", "Preço em massa"), ("emitir_recibo", "Emitir recibo")],
        },
    },
    {
        "nome": "Pagamentos a produtores / saldos",
        "app": "leite",
        "acoes": {
            "ver": "view_pagamentoprodutor", "criar": "add_pagamentoprodutor",
            "especial": [("estornar_pagamento", "Estornar pagamento")],
        },
    },
    {
        "nome": "Caixa (entradas e saídas)",
        "app": "financeiro",
        "acoes": {
            "ver": "view_lancamento", "criar": "add_lancamento",
            "especial": [("estornar_lancamento", "Estornar lançamento")],
        },
    },
    {
        "nome": "Categorias do caixa",
        "app": "financeiro",
        "acoes": {"ver": "view_categoria", "criar": "add_categoria", "editar": "change_categoria"},
    },
    {
        "nome": "Dados do laticínio",
        "app": "core",
        "acoes": {"ver": "view_dadosempresa", "editar": "change_dadosempresa"},
    },
    {
        "nome": "Backup",
        "app": "backup",
        "acoes": {"especial": [("gerenciar_backup", "Configurar, enviar e baixar backup")]},
    },
]

ACOES_SIMPLES = ["ver", "criar", "editar", "excluir"]


def codigos_permitidos():
    """Conjunto com todas as permissões da lista, no formato 'app.codename'."""
    codigos = set()
    for modulo in MODULOS:
        for acao, valor in modulo["acoes"].items():
            if acao == "especial":
                codigos.update(f"{modulo['app']}.{codename}" for codename, _ in valor)
            else:
                codigos.add(f"{modulo['app']}.{valor}")
    return codigos


def todas_menos(*excluir):
    return sorted(codigos_permitidos() - set(excluir))


NIVEIS_PADRAO = {
    # Gerente: tudo, menos usuários (só o Administrador mexe em usuários).
    "Gerente": todas_menos(),
    # Escritório: lança e corrige leite, emite recibos, registra pagamentos e caixa. Não estorna nem apaga produtor.
    "Escritório": [
        "leite.registrar_coleta_diaria",
        "leite.view_produtor", "leite.add_produtor", "leite.change_produtor",
        "leite.view_coleta", "leite.add_coleta", "leite.change_coleta", "leite.delete_coleta",
        "leite.emitir_recibo",
        "leite.view_pagamentoprodutor", "leite.add_pagamentoprodutor",
        "financeiro.view_lancamento", "financeiro.add_lancamento", "financeiro.view_categoria",
        "core.view_dadosempresa",
    ],
    # Coletor: SOMENTE a página de coleta diária (inserir leite coletado/entregue).
    "Coletor": ["leite.registrar_coleta_diaria"],
}
