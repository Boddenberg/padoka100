"""Exportacao visual do snapshot de Analytics para PDF."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

LARANJA = colors.HexColor("#F47A36")
LARANJA_ESCURO = colors.HexColor("#A33E12")
CREME = colors.HexColor("#FFF8EF")
CREME_ESCURO = colors.HexColor("#F8E9D7")
VERDE = colors.HexColor("#2D7D5B")
VERMELHO = colors.HexColor("#C34B3F")
TINTA = colors.HexColor("#2C211B")
MUTED = colors.HexColor("#796A61")
BORDA = colors.HexColor("#E8D8C8")


def _numero(valor) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _dinheiro(valor) -> str:
    texto = f"{_numero(valor):,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _percentual(valor) -> str:
    return f"{_numero(valor):.1f}%".replace(".", ",")


def _estilos() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PadokaTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=27,
            textColor=colors.white,
            alignment=TA_LEFT,
            spaceAfter=6,
        ),
        "eyebrow": ParagraphStyle(
            "PadokaEyebrow",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#FFE6D4"),
            uppercase=True,
            tracking=1.1,
        ),
        "hero": ParagraphStyle(
            "PadokaHero",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.white,
        ),
        "h2": ParagraphStyle(
            "PadokaH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=19,
            textColor=TINTA,
            spaceBefore=7,
            spaceAfter=8,
        ),
        "h3": ParagraphStyle(
            "PadokaH3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=TINTA,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "PadokaBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=TINTA,
        ),
        "small": ParagraphStyle(
            "PadokaSmall",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
        "kpi_label": ParagraphStyle(
            "PadokaKpiLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "kpi_value": ParagraphStyle(
            "PadokaKpiValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=TINTA,
            alignment=TA_CENTER,
        ),
    }


def _cabecalho_rodape(canvas, doc) -> None:
    canvas.saveState()
    largura, altura = A4
    canvas.setStrokeColor(BORDA)
    canvas.line(18 * mm, 14 * mm, largura - 18 * mm, 14 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18 * mm, 9 * mm, "PADOKA 100% - Relatorio de Analytics")
    canvas.drawRightString(largura - 18 * mm, 9 * mm, f"Pagina {doc.page}")
    canvas.restoreState()


def _grafico_linha(serie: list[dict]) -> Drawing:
    largura, altura = 500, 165
    desenho = Drawing(largura, altura)
    desenho.add(Rect(0, 0, largura, altura, fillColor=CREME, strokeColor=None, rx=12, ry=12))
    if not serie:
        desenho.add(String(20, 78, "Sem vendas registradas no periodo", fillColor=MUTED))
        return desenho
    valores = [_numero(item.get("faturamento")) for item in serie]
    maximo = max(max(valores), 1)
    esquerda, direita, base, topo = 42, largura - 18, 30, altura - 22
    for indice in range(4):
        y = base + ((topo - base) * indice / 3)
        desenho.add(Line(esquerda, y, direita, y, strokeColor=BORDA, strokeWidth=0.7))
    passo = (direita - esquerda) / max(len(serie) - 1, 1)
    pontos = []
    for indice, valor in enumerate(valores):
        x = esquerda + passo * indice
        y = base + (valor / maximo) * (topo - base)
        pontos.extend([x, y])
    if len(pontos) >= 4:
        desenho.add(PolyLine(pontos, strokeColor=LARANJA, strokeWidth=2.7))
    for indice in {0, len(serie) // 2, len(serie) - 1}:
        item = serie[indice]
        x = esquerda + passo * indice
        y = base + (valores[indice] / maximo) * (topo - base)
        desenho.add(Circle(x, y, 3.2, fillColor=LARANJA, strokeColor=colors.white))
        rotulo = str(item.get("data") or "")[-5:]
        desenho.add(String(x - 13, 12, rotulo, fontSize=7, fillColor=MUTED))
    desenho.add(String(12, topo - 2, _dinheiro(maximo), fontSize=7, fillColor=MUTED))
    desenho.add(String(12, base - 2, "R$ 0", fontSize=7, fillColor=MUTED))
    return desenho


def _grafico_produtos(produtos: list[dict]) -> Drawing:
    itens = produtos[:6]
    altura = max(95, 26 + len(itens) * 27)
    desenho = Drawing(500, altura)
    desenho.add(Rect(0, 0, 500, altura, fillColor=CREME, strokeColor=None, rx=12, ry=12))
    if not itens:
        desenho.add(String(20, 42, "Sem produtos vendidos no periodo", fillColor=MUTED))
        return desenho
    maximo = max(_numero(item.get("faturamento")) for item in itens) or 1
    for indice, item in enumerate(itens):
        y = altura - 28 - indice * 27
        nome = str(item.get("nome") or "Produto")[:28]
        valor = _numero(item.get("faturamento"))
        largura_barra = 220 * valor / maximo
        desenho.add(String(14, y + 4, nome, fontSize=8, fillColor=TINTA))
        desenho.add(Rect(168, y, 220, 10, fillColor=CREME_ESCURO, strokeColor=None, rx=5, ry=5))
        desenho.add(
            Rect(
                168,
                y,
                largura_barra,
                10,
                fillColor=LARANJA,
                strokeColor=None,
                rx=5,
                ry=5,
            )
        )
        desenho.add(String(398, y + 2, _dinheiro(valor), fontSize=7.5, fillColor=MUTED))
    return desenho


def _kpi(titulo: str, valor: str, estilos: dict) -> list:
    return [
        Paragraph(escape(titulo.upper()), estilos["kpi_label"]),
        Spacer(1, 3),
        Paragraph(escape(valor), estilos["kpi_value"]),
    ]


def _lista(itens: list[str], estilos: dict, *, cor=LARANJA) -> list:
    elementos = []
    for item in itens:
        tabela = Table(
            [["", Paragraph(escape(str(item)), estilos["body"])]],
            colWidths=[4 * mm, 156 * mm],
        )
        tabela.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), cor),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (1, 0), (1, 0), 8),
                ]
            )
        )
        elementos.append(tabela)
    return elementos


def gerar_pdf(relatorio: dict) -> bytes:
    conteudo = relatorio["conteudo"]
    indicadores = conteudo["indicadores"]
    periodo = conteudo["periodo"]
    estilos = _estilos()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=19 * mm,
        title=relatorio.get("titulo") or "Relatorio de Analytics Padoka 100%",
        author="Padoka 100%",
    )
    tipo = "INTELIGENCIA ARTIFICIAL" if relatorio.get("tipo") == "ia" else "ANALYTICS"
    hero = Table(
        [
            [Paragraph(f"RELATORIO {tipo}", estilos["eyebrow"])],
            [Paragraph(escape(relatorio.get("titulo") or "Raio-X do negocio"), estilos["title"])],
            [
                Paragraph(
                    escape(
                        f"{periodo.get('rotulo', '')} | "
                        f"{periodo.get('dias_com_operacao', 0)} dias com operacao"
                    ),
                    estilos["hero"],
                )
            ],
        ],
        colWidths=[174 * mm],
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LARANJA_ESCURO),
                ("BOX", (0, 0), (-1, -1), 0, LARANJA_ESCURO),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
                ("TOPPADDING", (0, 0), (-1, 0), 15),
                ("TOPPADDING", (0, 1), (-1, -1), 5),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 15),
            ]
        )
    )
    story = [hero, Spacer(1, 12), Paragraph("Os numeros que importam", estilos["h2"])]
    kpis = [
        _kpi("Faturamento", _dinheiro(indicadores["faturamento"]), estilos),
        _kpi("Lucro estimado", _dinheiro(indicadores["lucro_estimado"]), estilos),
        _kpi("Ticket medio", _dinheiro(indicadores["ticket_medio"]), estilos),
        _kpi("Vendas", str(indicadores["quantidade_vendas"]), estilos),
        _kpi("Eficiencia", _percentual(indicadores["eficiencia_venda_percentual"]), estilos),
        _kpi("Sobras", str(indicadores["unidades_sobrando"]), estilos),
    ]
    tabela_kpi = Table([kpis[:3], kpis[3:]], colWidths=[58 * mm] * 3, rowHeights=[28 * mm] * 2)
    tabela_kpi.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CREME),
                ("BOX", (0, 0), (-1, -1), 0.8, BORDA),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDA),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    story.extend(
        [
            tabela_kpi,
            Spacer(1, 12),
            Paragraph("Evolucao do faturamento", estilos["h2"]),
            _grafico_linha(conteudo.get("serie_diaria") or []),
            Spacer(1, 10),
            Paragraph("Produtos que puxaram o resultado", estilos["h2"]),
            _grafico_produtos(conteudo.get("produtos") or []),
            Spacer(1, 10),
        ]
    )
    comparacao = conteudo.get("comparacao", {}).get("faturamento", {})
    variacao = comparacao.get("variacao_percentual")
    if variacao is None:
        texto_comparacao = "Primeiro resultado com base comparavel registrada."
    else:
        sentido = "acima" if _numero(variacao) >= 0 else "abaixo"
        texto_comparacao = (
            f"Faturamento {_percentual(abs(_numero(variacao)))} {sentido} do periodo anterior, "
            f"uma diferenca de {_dinheiro(abs(_numero(comparacao.get('diferenca'))))}."
        )
    comparacao_box = Table(
        [
            [
                Paragraph("COMPARACAO", estilos["kpi_label"]),
                Paragraph(escape(texto_comparacao), estilos["body"]),
            ]
        ],
        colWidths=[31 * mm, 143 * mm],
    )
    comparacao_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CREME),
                ("BOX", (0, 0), (-1, -1), 0.8, BORDA),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.extend([comparacao_box, PageBreak()])

    ia = conteudo.get("ia")
    if ia:
        story.extend(
            [
                Paragraph("Leitura estrategica do Paozinho", estilos["h2"]),
                Paragraph(escape(str(ia.get("resumo") or "")), estilos["body"]),
                Spacer(1, 8),
                Paragraph("Principais achados", estilos["h3"]),
                *_lista(ia.get("principais_achados") or [], estilos),
                Spacer(1, 7),
                Paragraph("Acoes recomendadas", estilos["h3"]),
                *_lista(ia.get("acoes_recomendadas") or [], estilos, cor=VERDE),
                Spacer(1, 9),
            ]
        )

    story.append(Paragraph("Oportunidades para a proxima semana", estilos["h2"]))
    oportunidades = conteudo.get("oportunidades") or []
    for item in oportunidades:
        story.append(
            KeepTogether(
                [
                    Paragraph(escape(str(item.get("titulo") or "Oportunidade")), estilos["h3"]),
                    Paragraph(escape(str(item.get("descricao") or "")), estilos["body"]),
                    Spacer(1, 8),
                ]
            )
        )
    alertas = conteudo.get("alertas") or []
    if alertas:
        story.extend([Spacer(1, 5), Paragraph("Pontos de atencao", estilos["h2"])])
        story.extend(
            _lista(
                [f"{item.get('titulo')}. {item.get('descricao')}" for item in alertas],
                estilos,
                cor=VERMELHO,
            )
        )

    story.extend(
        [
            Spacer(1, 12),
            HRFlowable(width="100%", thickness=0.8, color=BORDA),
            Spacer(1, 10),
            Paragraph("Como ler este relatorio", estilos["h2"]),
            *_lista(conteudo.get("metodologia") or [], estilos),
            Spacer(1, 8),
            Paragraph(
                escape(str(conteudo.get("qualidade_dados", {}).get("mensagem") or "")),
                estilos["small"],
            ),
        ]
    )
    doc.build(story, onFirstPage=_cabecalho_rodape, onLaterPages=_cabecalho_rodape)
    return buffer.getvalue()
