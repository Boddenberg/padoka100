from datetime import date
from decimal import Decimal
from uuid import UUID

from app.db.supabase import get_supabase_client
from app.modules.dias_de_venda import servico as servico_de_dias_de_venda


def buscar_resumo_do_dia_de_venda(dia_de_venda_id: UUID) -> dict:
    client = get_supabase_client()
    dia_de_venda = servico_de_dias_de_venda.buscar_linha_dia_de_venda(client, dia_de_venda_id)
    itens_producao = (
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .execute()
        .data
    )
    vendas_ativas = (
        client.table("vendas")
        .select("id")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .eq("situacao", "ativa")
        .execute()
        .data
    )
    venda_ids = [venda["id"] for venda in vendas_ativas]
    itens_venda = []
    if venda_ids:
        itens_venda = (
            client.table("itens_venda")
            .select("*")
            .in_("venda_id", venda_ids)
            .execute()
            .data
        )
    decisoes_sobra = (
        client.table("decisoes_sobra")
        .select("*")
        .eq("dia_destino_id", str(dia_de_venda_id))
        .execute()
        .data
    )

    produtos = _montar_resumos_dos_produtos(itens_producao, itens_venda, decisoes_sobra)
    totais = _somar_produtos(produtos)
    return {
        "dia_de_venda_id": dia_de_venda["id"],
        "data_venda": dia_de_venda["data_venda"],
        "nome_local": dia_de_venda.get("nome_local_no_momento"),
        "situacao": dia_de_venda["situacao"],
        **totais,
        "produtos": produtos,
    }


def buscar_resumo_do_periodo(data_inicio: date, data_fim: date) -> dict:
    client = get_supabase_client()
    dias = (
        client.table("dias_de_venda")
        .select("id")
        .gte("data_venda", data_inicio.isoformat())
        .lte("data_venda", data_fim.isoformat())
        .order("data_venda")
        .execute()
        .data
    )
    resumos_dias = [buscar_resumo_do_dia_de_venda(UUID(dia["id"])) for dia in dias]
    totais = _somar_dias(resumos_dias)
    return {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        **totais,
        "dias": resumos_dias,
    }


def _montar_resumos_dos_produtos(
    itens_producao: list[dict],
    itens_venda: list[dict],
    decisoes_sobra: list[dict],
) -> list[dict]:
    resumos: dict[str, dict] = {}

    for item in itens_producao:
        produto_id = item["produto_id"]
        resumos[produto_id] = {
            "produto_id": produto_id,
            "nome_produto": item["nome_produto_no_momento"],
            "url_imagem_produto": item.get("url_imagem_produto_no_momento"),
            "quantidade_produzida": item["quantidade_produzida"],
            "quantidade_sobra_aproveitada": 0,
            "quantidade_disponivel": item["quantidade_produzida"],
            "quantidade_vendida": 0,
            "quantidade_sobra": item["quantidade_produzida"],
            "faturamento_bruto": Decimal("0"),
            "custo_estimado": Decimal("0"),
            "lucro_estimado": Decimal("0"),
        }

    for item in decisoes_sobra:
        quantidade_usada = item["quantidade_usada_hoje"]
        if quantidade_usada <= 0:
            continue
        produto_id = item["produto_id"]
        if produto_id not in resumos:
            resumos[produto_id] = {
                "produto_id": produto_id,
                "nome_produto": item["nome_produto_no_momento"],
                "url_imagem_produto": item.get("url_imagem_produto_no_momento"),
                "quantidade_produzida": 0,
                "quantidade_sobra_aproveitada": 0,
                "quantidade_disponivel": 0,
                "quantidade_vendida": 0,
                "quantidade_sobra": 0,
                "faturamento_bruto": Decimal("0"),
                "custo_estimado": Decimal("0"),
                "lucro_estimado": Decimal("0"),
            }
        resumo = resumos[produto_id]
        resumo["quantidade_sobra_aproveitada"] += quantidade_usada
        resumo["quantidade_disponivel"] = (
            resumo["quantidade_produzida"] + resumo["quantidade_sobra_aproveitada"]
        )
        resumo["quantidade_sobra"] = resumo["quantidade_disponivel"] - resumo["quantidade_vendida"]

    for item in itens_venda:
        produto_id = item["produto_id"]
        if produto_id not in resumos:
            resumos[produto_id] = {
                "produto_id": produto_id,
                "nome_produto": item["nome_produto_no_momento"],
                "url_imagem_produto": item.get("url_imagem_produto_no_momento"),
                "quantidade_produzida": 0,
                "quantidade_sobra_aproveitada": 0,
                "quantidade_disponivel": 0,
                "quantidade_vendida": 0,
                "quantidade_sobra": 0,
                "faturamento_bruto": Decimal("0"),
                "custo_estimado": Decimal("0"),
                "lucro_estimado": Decimal("0"),
            }
        resumo = resumos[produto_id]
        resumo["quantidade_vendida"] += item["quantidade"]
        resumo["faturamento_bruto"] += Decimal(str(item["valor_total_venda"]))
        resumo["custo_estimado"] += Decimal(str(item["valor_total_custo"]))
        resumo["lucro_estimado"] = resumo["faturamento_bruto"] - resumo["custo_estimado"]
        resumo["quantidade_sobra"] = resumo["quantidade_disponivel"] - resumo["quantidade_vendida"]

    return sorted(resumos.values(), key=lambda produto: produto["nome_produto"])


def _somar_produtos(produtos: list[dict]) -> dict:
    return {
        "total_produzido": sum(produto["quantidade_produzida"] for produto in produtos),
        "total_sobra_aproveitada": sum(
            produto["quantidade_sobra_aproveitada"] for produto in produtos
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


def _somar_dias(dias: list[dict]) -> dict:
    return {
        "total_produzido": sum(dia["total_produzido"] for dia in dias),
        "total_sobra_aproveitada": sum(dia["total_sobra_aproveitada"] for dia in dias),
        "total_disponivel": sum(dia["total_disponivel"] for dia in dias),
        "total_vendido": sum(dia["total_vendido"] for dia in dias),
        "total_sobra": sum(dia["total_sobra"] for dia in dias),
        "faturamento_bruto": sum((dia["faturamento_bruto"] for dia in dias), Decimal("0")),
        "custo_estimado": sum((dia["custo_estimado"] for dia in dias), Decimal("0")),
        "lucro_estimado": sum((dia["lucro_estimado"] for dia in dias), Decimal("0")),
    }
