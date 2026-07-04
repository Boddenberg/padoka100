from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from supabase import Client

from app.core.errors import BadRequestError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.dias_de_venda import servico as servico_de_dias_de_venda
from app.modules.produtos import servico as servico_de_produtos
from app.modules.vendas.esquemas import RequisicaoCancelarVenda, RequisicaoRegistrarVenda
from app.shared.db import first_or_none, to_db_payload
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo


def registrar_venda(requisicao: RequisicaoRegistrarVenda) -> dict:
    client = get_supabase_client()
    dia_de_venda = servico_de_dias_de_venda.buscar_linha_dia_de_venda(
        client,
        requisicao.dia_de_venda_id,
    )
    if dia_de_venda["situacao"] == "fechado":
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

    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="venda_registrada",
        titulo="Venda registrada",
        tipo_entidade="venda",
        entidade_id=venda["id"],
        dia_de_venda_id=requisicao.dia_de_venda_id,
        detalhes={
            "tipo_entrada": requisicao.tipo_entrada,
            "itens": [
                {"produto_id": str(item.produto_id), "quantidade": item.quantidade}
                for item in requisicao.itens
            ],
        },
    )
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
                    "cancelado_em": datetime.now(timezone.utc),
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


def _montar_dados_item_vendido(
    venda_id: str,
    dia_de_venda: dict,
    produto_id: UUID,
    quantidade: int,
) -> dict:
    data_venda = date.fromisoformat(dia_de_venda["data_venda"])
    snapshot = servico_de_produtos.buscar_snapshot_do_produto(produto_id, data_venda)
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
