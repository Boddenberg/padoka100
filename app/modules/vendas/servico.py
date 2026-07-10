from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.errors import BadRequestError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.dias_de_venda import servico as servico_de_dias_de_venda
from app.modules.produtos import public as produtos_public
from app.modules.vendas.domain.availability import (
    calcular_quantidade_disponivel,
    calcular_quantidade_vendida,
    esgotou_com_a_venda,
)
from app.modules.vendas.esquemas import RequisicaoCancelarVenda, RequisicaoRegistrarVenda
from app.shared.db import first_or_none, to_db_payload
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo
from supabase import Client


def registrar_venda(
    requisicao: RequisicaoRegistrarVenda,
    *,
    permitir_dia_fechado: bool = False,
    detalhes_evento: dict[str, Any] | None = None,
) -> dict:
    client = get_supabase_client()
    dia_de_venda = servico_de_dias_de_venda.buscar_linha_dia_de_venda(
        client,
        requisicao.dia_de_venda_id,
    )
    if dia_de_venda["situacao"] == "fechado" and not permitir_dia_fechado:
        raise BadRequestError("Nao e possivel registrar venda em um dia fechado.")

    dados_venda = to_db_payload(
        {
            "dia_de_venda_id": requisicao.dia_de_venda_id,
            "tipo_entrada": requisicao.tipo_entrada,
            "interacao_ia_id": requisicao.interacao_ia_id,
            "texto_original": requisicao.texto_original,
            "url_audio": requisicao.url_audio,
            "observacoes": requisicao.observacoes,
            "ocorrido_em": requisicao.ocorrido_em,
            "situacao": "ativa",
        }
    )
    venda = client.table("vendas").insert(dados_venda).execute().data[0]
    linhas_itens = [
        _montar_dados_item_vendido(venda["id"], dia_de_venda, item.produto_id, item.quantidade)
        for item in requisicao.itens
    ]
    client.table("itens_venda").insert(linhas_itens).execute()

    detalhes = {
        "tipo_entrada": requisicao.tipo_entrada,
        "itens": [
            {
                "produto_id": item["produto_id"],
                "produto": item["nome_produto_no_momento"],
                "quantidade": item["quantidade"],
                "valor_total": item["valor_total_venda"],
            }
            for item in linhas_itens
        ],
    }
    if detalhes_evento:
        detalhes.update(detalhes_evento)

    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="VENDA_REALIZADA",
        titulo="Venda registrada",
        tipo_entidade="venda",
        entidade_id=venda["id"],
        dia_de_venda_id=requisicao.dia_de_venda_id,
        detalhes=detalhes,
    )
    _registrar_eventos_de_esgotamento(client, dia_de_venda, linhas_itens)
    return buscar_venda(UUID(venda["id"]))


def listar_vendas(dia_de_venda_id: UUID) -> list[dict]:
    client = get_supabase_client()
    servico_de_dias_de_venda.buscar_linha_dia_de_venda(client, dia_de_venda_id)
    vendas = (
        client.table("vendas")
        .select("*")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .order("ocorrido_em", desc=True)
        .execute()
        .data
    )
    return _anexar_itens_as_vendas(client, vendas)


def buscar_venda(venda_id: UUID) -> dict:
    client = get_supabase_client()
    venda = _buscar_linha_venda(client, venda_id)
    return _anexar_itens_as_vendas(client, [venda])[0]


def cancelar_venda(venda_id: UUID, requisicao: RequisicaoCancelarVenda) -> dict:
    client = get_supabase_client()
    venda = _buscar_linha_venda(client, venda_id)
    if venda["situacao"] == "cancelada":
        return _anexar_itens_as_vendas(client, [venda])[0]

    venda_atualizada = (
        client.table("vendas")
        .update(
            to_db_payload(
                {
                    "situacao": "cancelada",
                    "cancelado_em": datetime.now(UTC),
                    "motivo_cancelamento": requisicao.motivo,
                }
            )
        )
        .eq("id", str(venda_id))
        .execute()
        .data[0]
    )
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="venda_cancelada",
        titulo="Venda cancelada",
        tipo_entidade="venda",
        entidade_id=venda_id,
        dia_de_venda_id=venda_atualizada["dia_de_venda_id"],
        detalhes={"motivo": requisicao.motivo},
    )
    return _anexar_itens_as_vendas(client, [venda_atualizada])[0]


def _buscar_linha_venda(client: Client, venda_id: UUID | str) -> dict:
    venda = first_or_none(
        client.table("vendas").select("*").eq("id", str(venda_id)).limit(1).execute().data
    )
    if not venda:
        raise NotFoundError("Venda", str(venda_id))
    return venda


def _anexar_itens_as_vendas(client: Client, vendas: list[dict]) -> list[dict]:
    venda_ids = [venda["id"] for venda in vendas]
    if not venda_ids:
        return []
    itens = client.table("itens_venda").select("*").in_("venda_id", venda_ids).execute().data
    itens_agrupados = defaultdict(list)
    for item in itens:
        itens_agrupados[item["venda_id"]].append(item)
    for venda in vendas:
        venda["itens"] = itens_agrupados[venda["id"]]
    return vendas


def _registrar_eventos_de_esgotamento(
    client: Client,
    dia_de_venda: dict,
    itens_vendidos: list[dict],
) -> None:
    itens_por_produto = defaultdict(lambda: {"quantidade": 0, "produto": None})
    for item in itens_vendidos:
        produto_id = item["produto_id"]
        itens_por_produto[produto_id]["quantidade"] += item["quantidade"]
        itens_por_produto[produto_id]["produto"] = item

    for produto_id, resumo_item in itens_por_produto.items():
        quantidade_disponivel = _calcular_quantidade_disponivel_do_produto(
            client,
            dia_de_venda["id"],
            produto_id,
        )
        quantidade_vendida = _calcular_quantidade_vendida_ativa_do_produto(
            client,
            dia_de_venda["id"],
            produto_id,
        )
        if not esgotou_com_a_venda(
            quantidade_disponivel=quantidade_disponivel,
            quantidade_vendida_atual=quantidade_vendida,
            quantidade_vendida_nesta_venda=resumo_item["quantidade"],
        ):
            continue

        item = resumo_item["produto"]
        registrar_evento_na_linha_do_tempo(
            client,
            tipo_evento="PRODUTO_ESGOTADO",
            titulo=f"Produto esgotado: {item['nome_produto_no_momento']}",
            tipo_entidade="produto",
            entidade_id=produto_id,
            dia_de_venda_id=dia_de_venda["id"],
            detalhes={
                "produto_id": produto_id,
                "produto": item["nome_produto_no_momento"],
                "quantidade_disponivel": quantidade_disponivel,
                "quantidade_vendida": quantidade_vendida,
            },
        )


def _calcular_quantidade_disponivel_do_produto(
    client: Client,
    dia_de_venda_id: UUID | str,
    produto_id: UUID | str,
) -> int:
    itens_producao = (
        client.table("itens_producao")
        .select("quantidade_produzida")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .eq("produto_id", str(produto_id))
        .execute()
        .data
    )
    decisoes_sobra = (
        client.table("decisoes_sobra")
        .select("quantidade_usada_hoje")
        .eq("dia_destino_id", str(dia_de_venda_id))
        .eq("produto_id", str(produto_id))
        .execute()
        .data
    )
    return calcular_quantidade_disponivel(itens_producao, decisoes_sobra)


def _calcular_quantidade_vendida_ativa_do_produto(
    client: Client,
    dia_de_venda_id: UUID | str,
    produto_id: UUID | str,
) -> int:
    vendas_ativas = (
        client.table("vendas")
        .select("id")
        .eq("dia_de_venda_id", str(dia_de_venda_id))
        .eq("situacao", "ativa")
        .execute()
        .data
    )
    venda_ids = [venda["id"] for venda in vendas_ativas]
    if not venda_ids:
        return 0

    itens_venda = (
        client.table("itens_venda")
        .select("quantidade")
        .in_("venda_id", venda_ids)
        .eq("produto_id", str(produto_id))
        .execute()
        .data
    )
    return calcular_quantidade_vendida(itens_venda)


def _montar_dados_item_vendido(
    venda_id: str,
    dia_de_venda: dict,
    produto_id: UUID,
    quantidade: int,
) -> dict:
    data_venda = date.fromisoformat(dia_de_venda["data_venda"])
    snapshot = produtos_public.buscar_snapshot_do_produto(produto_id, data_venda)
    produto = snapshot["produto"]
    preco = snapshot["preco"]
    preco_venda = Decimal(str(preco["preco_venda"]))
    preco_custo = Decimal(str(preco["preco_custo"]))
    return to_db_payload(
        {
            "venda_id": venda_id,
            "dia_de_venda_id": dia_de_venda["id"],
            "produto_id": produto_id,
            "nome_produto_no_momento": produto["nome"],
            "url_imagem_produto_no_momento": produto.get("url_imagem_principal"),
            "versao_preco_id": preco["id"],
            "preco_venda_unitario_no_momento": preco_venda,
            "preco_custo_unitario_no_momento": preco_custo,
            "quantidade": quantidade,
            "valor_total_venda": preco_venda * quantidade,
            "valor_total_custo": preco_custo * quantidade,
        }
    )
