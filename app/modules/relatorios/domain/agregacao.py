"""Consolidacao pura de resumos de venda.

Recebe linhas ja carregadas (producao, venda, sobras, resumos por dia) e devolve
as estruturas de resumo. Nao acessa Supabase, entao roda sem rede e e testavel.
"""

from decimal import Decimal


def _resumo_produto_vazio(
    produto_id: str,
    nome_produto: str,
    url_imagem_produto: str | None,
) -> dict:
    return {
        "produto_id": produto_id,
        "nome_produto": nome_produto,
        "url_imagem_produto": url_imagem_produto,
        "participou_da_venda": True,
        "esgotado": False,
        "quantidade_produzida": 0,
        "quantidade_sobra_aproveitada": 0,
        "quantidade_sobra_descartada": 0,
        "quantidade_disponivel": 0,
        "quantidade_vendida": 0,
        "quantidade_sobra": 0,
        "faturamento_bruto": Decimal("0"),
        "custo_estimado": Decimal("0"),
        "lucro_estimado": Decimal("0"),
    }


def montar_resumos_dos_produtos(
    itens_producao: list[dict],
    itens_venda: list[dict],
    decisoes_sobra: list[dict],
) -> list[dict]:
    resumos: dict[str, dict] = {}

    for item in itens_producao:
        produto_id = item["produto_id"]
        resumo = _resumo_produto_vazio(
            produto_id,
            item["nome_produto_no_momento"],
            item.get("url_imagem_produto_no_momento"),
        )
        resumo["quantidade_produzida"] = item["quantidade_produzida"]
        resumo["quantidade_disponivel"] = item["quantidade_produzida"]
        resumo["quantidade_sobra"] = item["quantidade_produzida"]
        resumos[produto_id] = resumo

    for item in decisoes_sobra:
        quantidade_usada = item["quantidade_usada_hoje"]
        quantidade_descartada = item["quantidade_nao_usada_hoje"]
        if quantidade_usada <= 0 and quantidade_descartada <= 0:
            continue
        produto_id = item["produto_id"]
        if produto_id not in resumos:
            resumos[produto_id] = _resumo_produto_vazio(
                produto_id,
                item["nome_produto_no_momento"],
                item.get("url_imagem_produto_no_momento"),
            )
        resumo = resumos[produto_id]
        resumo["quantidade_sobra_aproveitada"] += quantidade_usada
        resumo["quantidade_sobra_descartada"] += quantidade_descartada
        resumo["quantidade_disponivel"] = (
            resumo["quantidade_produzida"] + resumo["quantidade_sobra_aproveitada"]
        )
        resumo["quantidade_sobra"] = resumo["quantidade_disponivel"] - resumo["quantidade_vendida"]

    for item in itens_venda:
        produto_id = item["produto_id"]
        if produto_id not in resumos:
            resumos[produto_id] = _resumo_produto_vazio(
                produto_id,
                item["nome_produto_no_momento"],
                item.get("url_imagem_produto_no_momento"),
            )
        resumo = resumos[produto_id]
        resumo["quantidade_vendida"] += item["quantidade"]
        resumo["faturamento_bruto"] += Decimal(str(item["valor_total_venda"]))
        resumo["custo_estimado"] += Decimal(str(item["valor_total_custo"]))
        resumo["lucro_estimado"] = resumo["faturamento_bruto"] - resumo["custo_estimado"]
        resumo["quantidade_sobra"] = resumo["quantidade_disponivel"] - resumo["quantidade_vendida"]

    produtos = [finalizar_resumo_produto(produto) for produto in resumos.values()]
    produtos = [produto for produto in produtos if produto["participou_da_venda"]]
    return sorted(produtos, key=lambda produto: produto["nome_produto"])


def finalizar_resumo_produto(produto: dict) -> dict:
    participou = any(
        [
            produto["quantidade_produzida"] > 0,
            produto["quantidade_sobra_aproveitada"] > 0,
            produto["quantidade_sobra_descartada"] > 0,
            produto["quantidade_vendida"] > 0,
        ]
    )
    produto["participou_da_venda"] = participou
    produto["esgotado"] = (
        produto["quantidade_disponivel"] > 0
        and produto["quantidade_vendida"] >= produto["quantidade_disponivel"]
    )
    return produto


def somar_produtos(produtos: list[dict]) -> dict:
    return {
        "total_produzido": sum(produto["quantidade_produzida"] for produto in produtos),
        "total_sobra_aproveitada": sum(
            produto["quantidade_sobra_aproveitada"] for produto in produtos
        ),
        "total_sobra_descartada": sum(
            produto["quantidade_sobra_descartada"] for produto in produtos
        ),
        "total_disponivel": sum(produto["quantidade_disponivel"] for produto in produtos),
        "total_vendido": sum(produto["quantidade_vendida"] for produto in produtos),
        "total_sobra": sum(produto["quantidade_sobra"] for produto in produtos),
        "faturamento_bruto": sum(
            (produto["faturamento_bruto"] for produto in produtos),
            Decimal("0"),
        ),
        "custo_estimado": sum((produto["custo_estimado"] for produto in produtos), Decimal("0")),
        "lucro_estimado": sum((produto["lucro_estimado"] for produto in produtos), Decimal("0")),
    }


def somar_dias(dias: list[dict]) -> dict:
    return {
        "total_produzido": sum(dia["total_produzido"] for dia in dias),
        "total_sobra_aproveitada": sum(dia["total_sobra_aproveitada"] for dia in dias),
        "total_sobra_descartada": sum(dia["total_sobra_descartada"] for dia in dias),
        "total_disponivel": sum(dia["total_disponivel"] for dia in dias),
        "total_vendido": sum(dia["total_vendido"] for dia in dias),
        "total_sobra": sum(dia["total_sobra"] for dia in dias),
        "faturamento_bruto": sum((dia["faturamento_bruto"] for dia in dias), Decimal("0")),
        "custo_estimado": sum((dia["custo_estimado"] for dia in dias), Decimal("0")),
        "lucro_estimado": sum((dia["lucro_estimado"] for dia in dias), Decimal("0")),
    }


def agrupar_por_chave(linhas: list[dict], chave: str) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {}
    for linha in linhas:
        grupos.setdefault(str(linha[chave]), []).append(linha)
    return grupos


def consolidar_produtos_por_data(resumos: list[dict]) -> list[dict]:
    produtos_por_id: dict[str, dict] = {}
    for resumo in resumos:
        for produto in resumo["produtos"]:
            produto_id = produto["produto_id"]
            if produto_id not in produtos_por_id:
                produtos_por_id[produto_id] = {
                    **produto,
                    "faturamento_bruto": Decimal("0"),
                    "custo_estimado": Decimal("0"),
                    "lucro_estimado": Decimal("0"),
                    "quantidade_produzida": 0,
                    "quantidade_sobra_aproveitada": 0,
                    "quantidade_sobra_descartada": 0,
                    "quantidade_disponivel": 0,
                    "quantidade_vendida": 0,
                    "quantidade_sobra": 0,
                }
            acumulado = produtos_por_id[produto_id]
            acumulado["quantidade_produzida"] += produto["quantidade_produzida"]
            acumulado["quantidade_sobra_aproveitada"] += produto["quantidade_sobra_aproveitada"]
            acumulado["quantidade_sobra_descartada"] += produto["quantidade_sobra_descartada"]
            acumulado["quantidade_disponivel"] += produto["quantidade_disponivel"]
            acumulado["quantidade_vendida"] += produto["quantidade_vendida"]
            acumulado["faturamento_bruto"] += Decimal(str(produto["faturamento_bruto"]))
            acumulado["custo_estimado"] += Decimal(str(produto["custo_estimado"]))
            acumulado["lucro_estimado"] += Decimal(str(produto["lucro_estimado"]))
            acumulado["quantidade_sobra"] = (
                acumulado["quantidade_disponivel"] - acumulado["quantidade_vendida"]
            )
            acumulado["participou_da_venda"] = True
            acumulado["esgotado"] = (
                acumulado["quantidade_disponivel"] > 0
                and acumulado["quantidade_vendida"] >= acumulado["quantidade_disponivel"]
            )
    return sorted(produtos_por_id.values(), key=lambda produto: produto["nome_produto"])


def consolidar_resumos_da_mesma_data(resumos: list[dict]) -> dict:
    if len(resumos) == 1:
        return resumos[0]

    data_venda = resumos[0]["data_venda"]
    produtos = consolidar_produtos_por_data(resumos)
    totais = somar_produtos(produtos)
    historico = []
    correcoes = []
    locais = {resumo.get("nome_local") for resumo in resumos if resumo.get("nome_local")}
    for resumo in resumos:
        historico.extend(resumo.get("historico") or [])
        correcoes.extend(resumo.get("correcoes") or [])

    produtos_produzidos = [produto for produto in produtos if produto["quantidade_produzida"] > 0]
    produtos_vendidos = [produto for produto in produtos if produto["quantidade_vendida"] > 0]
    produtos_sobrando = [produto for produto in produtos if produto["quantidade_sobra"] > 0]
    produtos_esgotados = [produto for produto in produtos if produto["esgotado"]]
    dia_ids = [
        dia_id
        for resumo in resumos
        for dia_id in (resumo.get("dia_de_venda_ids") or [resumo["dia_de_venda_id"]])
    ]
    situacao = "aberto" if any(resumo["situacao"] == "aberto" for resumo in resumos) else "fechado"
    return {
        "dia_de_venda_id": resumos[-1]["dia_de_venda_id"],
        "dia_de_venda_ids": dia_ids,
        "quantidade_aberturas": len(dia_ids),
        "data_venda": data_venda,
        "data": data_venda,
        "nome_local": next(iter(locais)) if len(locais) == 1 else "Multiplas aberturas",
        "situacao": situacao,
        "status": situacao.upper(),
        **totais,
        "itens_vendidos": totais["total_vendido"],
        "faturamento_total": totais["faturamento_bruto"],
        "produtos": produtos,
        "produtos_produzidos": produtos_produzidos,
        "produtos_vendidos": produtos_vendidos,
        "produtos_sobrando": produtos_sobrando,
        "produtos_esgotados": produtos_esgotados,
        "historico": historico,
        "correcoes": correcoes,
    }


def consolidar_resumos_leves_por_data(resumos: list[dict]) -> list[dict]:
    resumos_por_data = agrupar_por_chave(resumos, "data_venda")
    return [
        consolidar_resumos_leves_da_mesma_data(resumos_por_data[data_venda])
        for data_venda in sorted(resumos_por_data)
    ]


def consolidar_resumos_leves_da_mesma_data(resumos: list[dict]) -> dict:
    if len(resumos) == 1:
        return resumos[0]

    totais = somar_dias(resumos)
    locais = {resumo.get("nome_local") for resumo in resumos if resumo.get("nome_local")}
    situacao = "aberto" if any(resumo["situacao"] == "aberto" for resumo in resumos) else "fechado"
    return {
        "dia_de_venda_id": resumos[-1]["dia_de_venda_id"],
        "data_venda": resumos[0]["data_venda"],
        "nome_local": next(iter(locais)) if len(locais) == 1 else "Multiplas aberturas",
        "situacao": situacao,
        **totais,
    }


def formatar_dias_leves(resumos: list[dict]) -> list[dict]:
    return [
        {
            "dia_de_venda_id": resumo["dia_de_venda_id"],
            "data_venda": resumo["data_venda"],
            "nome_local": resumo.get("nome_local"),
            "situacao": resumo["situacao"],
            "faturamento_bruto": resumo["faturamento_bruto"],
            "lucro_estimado": resumo["lucro_estimado"],
        }
        for resumo in resumos
    ]
