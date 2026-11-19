"""
leite/pdf.py
============
Gera o recibo do produtor em PDF com o ReportLab (mesmo visual do sistema antigo,
com as faltas destacadas em vermelho claro).
"""

import io

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape


def _br(valor, casas=2):
    """Número no formato brasileiro (1.234,56)."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_pdf_recibo(*, empresa, produtor, inicio, fim, resumo):
    """Monta o PDF em memória e devolve os bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=36,
                            title=f"Recibo {produtor.nome}")
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("Titulo", parent=estilos["Heading1"], fontName="Courier-Bold", fontSize=18,
                            alignment=1, spaceAfter=4)
    sub = ParagraphStyle("Sub", fontName="Courier", fontSize=10, alignment=1)
    texto = ParagraphStyle("Texto", parent=estilos["Normal"], fontName="Courier", fontSize=11, spaceAfter=5)

    historia = [
        # escape() evita que um nome com "<" quebre o PDF.
        Paragraph(f"<b>{escape(empresa.nome.upper())}</b>", titulo),
        Paragraph("Comprovante de Fornecimento de Leite", sub),
    ]
    if empresa.documento or empresa.cidade:
        historia.append(Paragraph(escape(" - ".join(filter(None, [empresa.documento, empresa.cidade]))), sub))
    historia += [
        Spacer(1, 14),
        Paragraph(f"<b>PRODUTOR:</b> {escape(produtor.nome)}", texto),
        Paragraph(f"<b>PERÍODO:</b> {inicio:%d/%m/%Y} até {fim:%d/%m/%Y}", texto),
        Paragraph(f"<b>EMISSÃO:</b> {timezone.localdate():%d/%m/%Y}", texto),
        Spacer(1, 8),
    ]

    linhas = [["Data", "Quantidade", "Preço/L", "Total", "Situação"]]
    linhas_falta = []
    for coleta in resumo["coletas"]:
        if coleta.falta:
            linhas_falta.append(len(linhas))
        linhas.append([
            coleta.data.strftime("%d/%m/%Y"),
            f"{_br(coleta.litros, 1)} L",
            f"R$ {_br(coleta.preco_litro)}",
            f"R$ {_br(coleta.valor_total)}",
            "FALTA" if coleta.falta else "Entregue",
        ])
    linhas.append(["TOTAL", f"{_br(resumo['total_litros'], 1)} L", "", f"R$ {_br(resumo['total_valor'])}", ""])

    tabela = Table(linhas, colWidths=[100, 105, 95, 115, 90], repeatRows=1)
    estilo = [
        ("FONTNAME", (0, 0), (-1, -1), "Courier"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Courier-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Courier-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]
    for indice in linhas_falta:
        estilo += [
            ("BACKGROUND", (0, indice), (-1, indice), colors.mistyrose),
            ("TEXTCOLOR", (4, indice), (4, indice), colors.red),
            ("FONTNAME", (4, indice), (4, indice), "Courier-Bold"),
        ]
    tabela.setStyle(TableStyle(estilo))
    historia += [tabela, Spacer(1, 10)]
    if resumo["faltas"]:
        historia.append(Paragraph(f"Dias com falta no período: {resumo['faltas']}", texto))
    historia += [
        Spacer(1, 36),
        Paragraph("Assinatura do Responsável: ___________________________",
                  ParagraphStyle("Ass", fontName="Courier", fontSize=11, alignment=1)),
    ]
    if empresa.responsavel:
        historia.append(Paragraph(escape(empresa.responsavel), ParagraphStyle("Resp", fontName="Courier", fontSize=10, alignment=1)))

    def rodape(canvas, _doc):
        """Assinatura discreta no rodapé de cada página."""
        canvas.saveState()
        canvas.setFont("Helvetica-Oblique", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(A4[0] / 2.0, 18, "Sistema desenvolvido por Bruno Rocha")
        canvas.restoreState()

    doc.build(historia, onFirstPage=rodape, onLaterPages=rodape)
    return buffer.getvalue()
