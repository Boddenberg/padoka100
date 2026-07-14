"""Calculos puros do snapshot de Analytics."""

from collections import defaultdict
from datetime import date, datetime

DIAS_SEMANA = [
    "Segunda",
    "Terca",
    "Quarta",
    "Quinta",
    "Sexta",
    "Sabado",
    "Domingo",
]


def _numero(valor) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _inteiro(valor) -> int:
    return int(round(_numero(valor)))


def _percentual(parte: float, total: float) -> float:
    return round((parte / total) * 100, 1) if total else 0.0


def _comparar(atual: float, anterior: float) -> dict:
    diferenca = atual - anterior
    if anterior:
        variacao = round((diferenca / abs(anterior)) * 100, 1)
        tendencia = "alta" if diferenca > 0 else "queda" if diferenca < 0 else "estavel"
    elif atual:
        variacao = None
        tendencia = "novo"
    else:
        variacao = 0.0
        tendencia = "estavel"
    return {
        "atual": round(atual, 2),
        "anterior": round(anterior, 2),
        "diferenca": round(diferenca, 2),
        "variacao_percentual": variacao,
        "tendencia": tendencia,
    }


def _indicadores(dados: dict) -> dict:
    faturamento = _numero(dados.get("faturamentoTotal"))
    custo = _numero(dados.get("custoEstimado"))
    lucro = _numero(dados.get("lucroEstimado"))
    produzido = _inteiro(dados.get("quantidadeTotalProduzida"))
    vendido = _inteiro(dados.get("quantidadeTotalVendida"))
    sobras = _inteiro(dados.get("quantidadeTotalSobrando"))
    vendas = _inteiro(dados.get("quantidadeVendas"))
    return {
        "faturamento": round(faturamento, 2),
        "custo_estimado": round(custo, 2),
        "lucro_estimado": round(lucro, 2),
        "margem_percentual": _percentual(lucro, faturamento),
        "quantidade_vendas": vendas,
        "ticket_medio": round(faturamento / vendas, 2) if vendas else 0.0,
        "unidades_produzidas": produzido,
        "unidades_vendidas": vendido,
        "unidades_sobrando": sobras,
        "sobras_reaproveitadas": _inteiro(dados.get("quantidadeSobraAproveitada")),
        "sobras_descartadas": _inteiro(dados.get("quantidadeSobraDescartada")),
        "eficiencia_venda_percentual": _percentual(vendido, produzido),
        "indice_sobra_percentual": _percentual(sobras, produzido),
    }


def _serie_diaria(dados: dict) -> list[dict]:
    serie = []
    for dia in dados.get("dias") or []:
        serie.append(
            {
                "data": dia.get("data"),
                "faturamento": round(_numero(dia.get("faturamentoTotal")), 2),
                "lucro": round(_numero(dia.get("lucroEstimado")), 2),
                "custo": round(_numero(dia.get("custoEstimado")), 2),
                "produzido": _inteiro(dia.get("quantidadeTotalProduzida")),
                "vendido": _inteiro(dia.get("quantidadeTotalVendida")),
                "sobra": _inteiro(dia.get("quantidadeTotalSobrando")),
                "vendas": _inteiro(dia.get("quantidadeVendas")),
                "local": dia.get("nomeLocal"),
            }
        )
    return serie


def _produtos(dados: dict, faturamento_total: float) -> list[dict]:
    produtos = []
    for produto in dados.get("produtos") or []:
        faturamento = _numero(produto.get("faturamento"))
        produzido = _inteiro(produto.get("totalProduzido"))
        vendido = _inteiro(produto.get("totalVendido"))
        sobra = _inteiro(produto.get("totalSobrando"))
        custo = _numero(produto.get("custoEstimado"))
        lucro = _numero(produto.get("lucroEstimado"))
        produtos.append(
            {
                "produto_id": produto.get("produtoId"),
                "nome": produto.get("produto") or "Produto",
                "faturamento": round(faturamento, 2),
                "participacao_percentual": _percentual(faturamento, faturamento_total),
                "custo_estimado": round(custo, 2),
                "lucro_estimado": round(lucro, 2),
                "margem_percentual": _percentual(lucro, faturamento),
                "produzido": produzido,
                "vendido": vendido,
                "sobra": sobra,
                "reaproveitado": _inteiro(produto.get("totalSobraAproveitada")),
                "descartado": _inteiro(produto.get("totalSobraDescartada")),
                "eficiencia_percentual": _percentual(vendido, produzido),
                "dias_esgotado": _inteiro(produto.get("diasEsgotado")),
            }
        )
    return sorted(produtos, key=lambda item: item["faturamento"], reverse=True)


def _desempenho_semana(serie: list[dict]) -> list[dict]:
    acumulado: dict[int, dict] = defaultdict(
        lambda: {"faturamento": 0.0, "vendido": 0, "sobra": 0, "dias": 0}
    )
    for item in serie:
        try:
            indice = date.fromisoformat(str(item["data"])).weekday()
        except (TypeError, ValueError):
            continue
        linha = acumulado[indice]
        linha["faturamento"] += item["faturamento"]
        linha["vendido"] += item["vendido"]
        linha["sobra"] += item["sobra"]
        linha["dias"] += 1
    return [
        {
            "dia": DIAS_SEMANA[indice],
            "faturamento": round(acumulado[indice]["faturamento"], 2),
            "media_faturamento": round(
                acumulado[indice]["faturamento"] / acumulado[indice]["dias"], 2
            ),
            "vendido": acumulado[indice]["vendido"],
            "sobra": acumulado[indice]["sobra"],
            "dias": acumulado[indice]["dias"],
        }
        for indice in range(7)
        if acumulado[indice]["dias"]
    ]


def _destaques(serie: list[dict], produtos: list[dict], comparacao: dict) -> list[dict]:
    destaques = []
    dias_com_receita = [item for item in serie if item["faturamento"] > 0]
    if dias_com_receita:
        melhor = max(dias_com_receita, key=lambda item: item["faturamento"])
        pior = min(dias_com_receita, key=lambda item: item["faturamento"])
        destaques.append(
            {
                "tipo": "melhor_dia",
                "titulo": "Melhor dia do periodo",
                "descricao": melhor["data"],
                "valor": melhor["faturamento"],
            }
        )
        if len(dias_com_receita) > 1:
            destaques.append(
                {
                    "tipo": "pior_dia",
                    "titulo": "Dia de menor movimento",
                    "descricao": pior["data"],
                    "valor": pior["faturamento"],
                }
            )
    if produtos:
        lider = produtos[0]
        destaques.append(
            {
                "tipo": "produto_lider",
                "titulo": "Produto que mais faturou",
                "descricao": lider["nome"],
                "valor": lider["faturamento"],
            }
        )
    tendencia = comparacao["faturamento"]
    if tendencia["tendencia"] in {"alta", "queda"}:
        destaques.append(
            {
                "tipo": "tendencia",
                "titulo": "Movimento do faturamento",
                "descricao": tendencia["tendencia"],
                "valor": tendencia["variacao_percentual"],
            }
        )
    return destaques


def _recomendacoes(indicadores: dict, produtos: list[dict], serie: list[dict]) -> tuple[list, list]:
    oportunidades: list[dict] = []
    alertas: list[dict] = []
    com_sobra = [item for item in produtos if item["sobra"] > 0]
    if com_sobra:
        alvo = max(com_sobra, key=lambda item: item["sobra"])
        oportunidades.append(
            {
                "titulo": f"Ajuste a producao de {alvo['nome']}",
                "descricao": (
                    f"O produto terminou o periodo com {alvo['sobra']} unidade(s) de sobra. "
                    "Teste uma reducao gradual e acompanhe os esgotamentos."
                ),
                "impacto": "reduzir_sobras",
            }
        )
    esgotados = [item for item in produtos if item["dias_esgotado"] > 0]
    if esgotados:
        alvo = max(esgotados, key=lambda item: item["dias_esgotado"])
        oportunidades.append(
            {
                "titulo": f"Proteja as vendas de {alvo['nome']}",
                "descricao": (
                    f"Houve esgotamento em {alvo['dias_esgotado']} dia(s). "
                    "Avalie produzir um pouco mais nos dias de maior procura."
                ),
                "impacto": "evitar_ruptura",
            }
        )
    if produtos:
        lider = produtos[0]
        oportunidades.append(
            {
                "titulo": f"Use {lider['nome']} como produto ancora",
                "descricao": (
                    f"Ele representa {lider['participacao_percentual']:.1f}% do faturamento. "
                    "Combine-o com produtos de boa margem para elevar o ticket medio."
                ),
                "impacto": "aumentar_ticket",
            }
        )
    if indicadores["indice_sobra_percentual"] >= 20:
        alertas.append(
            {
                "nivel": "alto",
                "titulo": "Sobra acima de 20% da producao",
                "descricao": "Revise quantidades por produto e por dia da semana.",
            }
        )
    if indicadores["margem_percentual"] <= 0 and indicadores["faturamento"] > 0:
        alertas.append(
            {
                "nivel": "alto",
                "titulo": "Margem estimada sem ganho",
                "descricao": "Confira custos e precos antes de ampliar a producao.",
            }
        )
    if not serie:
        alertas.append(
            {
                "nivel": "informativo",
                "titulo": "Ainda nao ha dias registrados no periodo",
                "descricao": "Registre producao e vendas para liberar comparacoes confiaveis.",
            }
        )
    return oportunidades[:4], alertas[:4]


def montar_relatorio(
    *,
    atual: dict,
    anterior: dict,
    tipo: str,
    gerado_em: datetime,
) -> dict:
    indicadores = _indicadores(atual)
    indicadores_anteriores = _indicadores(anterior)
    serie = _serie_diaria(atual)
    produtos = _produtos(atual, indicadores["faturamento"])
    comparacao = {
        "faturamento": _comparar(
            indicadores["faturamento"], indicadores_anteriores["faturamento"]
        ),
        "lucro": _comparar(
            indicadores["lucro_estimado"], indicadores_anteriores["lucro_estimado"]
        ),
        "unidades_vendidas": _comparar(
            indicadores["unidades_vendidas"],
            indicadores_anteriores["unidades_vendidas"],
        ),
        "ticket_medio": _comparar(
            indicadores["ticket_medio"], indicadores_anteriores["ticket_medio"]
        ),
    }
    oportunidades, alertas = _recomendacoes(indicadores, produtos, serie)
    produtos_com_venda = [item for item in produtos if item["vendido"] > 0]
    produtos_menos_vendidos = sorted(
        produtos_com_venda,
        key=lambda item: (item["vendido"], item["faturamento"]),
    )[:5]
    produtos_com_custo = [item for item in produtos_com_venda if item["custo_estimado"] > 0]
    cobertura_custos = _percentual(len(produtos_com_custo), len(produtos_com_venda))
    dias_operacao = len(serie)
    score = min(
        100,
        round(
            (40 if dias_operacao >= 7 else dias_operacao * 5)
            + cobertura_custos * 0.35
            + (25 if anterior.get("dias") else 0)
        ),
    )
    qualidade = "alta" if score >= 75 else "media" if score >= 45 else "inicial"
    return {
        "versao": 1,
        "tipo": tipo,
        "gerado_em": gerado_em.isoformat(),
        "periodo": {
            **(atual.get("periodo") or {}),
            "dias_calendario": (
                date.fromisoformat(atual["periodo"]["fim"])
                - date.fromisoformat(atual["periodo"]["inicio"])
            ).days
            + 1,
            "dias_com_operacao": dias_operacao,
        },
        "indicadores": indicadores,
        "comparacao": comparacao,
        "serie_diaria": serie,
        "produtos": produtos,
        "rankings": {
            "mais_vendidos": sorted(
                produtos, key=lambda item: item["vendido"], reverse=True
            )[:5],
            "menos_vendidos": produtos_menos_vendidos,
            "maiores_sobras": sorted(
                produtos, key=lambda item: item["sobra"], reverse=True
            )[:5],
            "maiores_margens": sorted(
                produtos_com_venda,
                key=lambda item: item["margem_percentual"],
                reverse=True,
            )[:5],
        },
        "desempenho_semana": _desempenho_semana(serie),
        "horarios": atual.get("vendasPorHora") or [],
        "destaques": _destaques(serie, produtos, comparacao),
        "oportunidades": oportunidades,
        "alertas": alertas,
        "qualidade_dados": {
            "score": score,
            "nivel": qualidade,
            "dias_analisados": dias_operacao,
            "produtos_analisados": len(produtos),
            "cobertura_custos_percentual": cobertura_custos,
            "mensagem": (
                "Quanto mais dias, custos e producao forem registrados, "
                "mais precisas ficam as recomendacoes."
            ),
        },
        "metodologia": [
            "Vendas canceladas nao entram nos calculos.",
            "Custos e lucros usam os valores salvos no momento da venda.",
            "O periodo anterior tem a mesma quantidade de dias e termina na vespera.",
            "Sobras consideram producao, vendas e reaproveitamentos registrados.",
        ],
    }
