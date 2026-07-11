"""Correcao retroativa de um dia de venda ja fechado.

Cobre producao, itens de venda, vendas adicionadas e vendas canceladas, sempre
registrando a auditoria em `correcoes_dia_fechado` e na linha do tempo.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from app.core.errors import BadRequestError, NotFoundError
from app.infra.supabase.client import get_supabase_client
from app.infra.supabase.payload import first_or_none, to_db_payload
from app.modules.dias_de_venda import servico as servico_dias
from app.modules.dias_de_venda.esquemas import (
    RequisicaoCorrigirDiaFechado,
    RequisicaoCorrigirItemVendaDiaFechado,
    RequisicaoCorrigirProducaoDiaFechado,
    RequisicaoVendaRetroativaDiaFechado,
)
from app.modules.produtos import public as produtos_public
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo
from supabase import Client


def corrigir_dia_fechado(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoCorrigirDiaFechado,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    client = get_supabase_client()
    dia_de_venda = servico_dias.buscar_linha_dia_de_venda(
        client,
        dia_de_venda_id,
        usuario_id=usuario_id,
    )
    if dia_de_venda["situacao"] != "fechado":
        raise BadRequestError("Somente dias fechados podem receber correcao retroativa.")

    if not any(
        [
            requisicao.producoes,
            requisicao.itens_venda,
            requisicao.vendas_adicionadas,
            requisicao.vendas_canceladas,
        ]
    ):
        raise BadRequestError("Informe ao menos uma alteracao para corrigir o dia fechado.")

    alteracoes: list[dict] = []
    for producao in requisicao.producoes:
        alteracao = _corrigir_producao_em_dia_fechado(
            client,
            dia_de_venda,
            producao,
            usuario_id=usuario_id,
        )
        if alteracao:
            alteracoes.append(alteracao)

    for item_venda in requisicao.itens_venda:
        alteracao = _corrigir_item_venda_em_dia_fechado(client, dia_de_venda, item_venda)
        if alteracao:
            alteracoes.append(alteracao)

    for venda_retroativa in requisicao.vendas_adicionadas:
        alteracoes.append(
            _registrar_venda_retroativa_em_dia_fechado(dia_de_venda, venda_retroativa)
        )

    for cancelamento in requisicao.vendas_canceladas:
        alteracao = _cancelar_venda_em_correcao(
            dia_de_venda,
            cancelamento.venda_id,
            cancelamento.motivo,
        )
        if alteracao:
            alteracoes.append(alteracao)

    if not alteracoes:
        raise BadRequestError("Nenhuma alteracao aplicavel foi encontrada para a correcao.")

    correcao = (
        client.table("correcoes_dia_fechado")
        .insert(
            to_db_payload(
                {
                    "dia_de_venda_id": dia_de_venda_id,
                    "usuario_id": str(usuario_id) if usuario_id else None,
                    "motivo": requisicao.motivo,
                    "alteracoes": alteracoes,
                }
            )
        )
        .execute()
        .data[0]
    )
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="CORRECAO_DIA_FECHADO",
        titulo=f"Correcao retroativa: {dia_de_venda['data_venda']}",
        tipo_entidade="dia_de_venda",
        entidade_id=dia_de_venda_id,
        dia_de_venda_id=dia_de_venda_id,
        usuario_id=usuario_id,
        detalhes={
            "correcao_id": correcao["id"],
            "usuario_id": str(usuario_id) if usuario_id else None,
            "motivo": requisicao.motivo,
            "alteracoes": alteracoes,
        },
    )
    return correcao


def _corrigir_producao_em_dia_fechado(
    client: Client,
    dia_de_venda: dict,
    requisicao: RequisicaoCorrigirProducaoDiaFechado,
    *,
    usuario_id: UUID | str | None = None,
) -> dict | None:
    existente = first_or_none(
        client.table("itens_producao")
        .select("*")
        .eq("dia_de_venda_id", dia_de_venda["id"])
        .eq("produto_id", str(requisicao.produto_id))
        .limit(1)
        .execute()
        .data
    )
    if existente:
        return _atualizar_producao_existente_em_correcao(client, existente, requisicao)
    return _adicionar_producao_em_correcao(
        client,
        dia_de_venda,
        requisicao,
        usuario_id=usuario_id,
    )


def _atualizar_producao_existente_em_correcao(
    client: Client,
    existente: dict,
    requisicao: RequisicaoCorrigirProducaoDiaFechado,
) -> dict | None:
    dados_atualizacao = {"quantidade_produzida": requisicao.quantidade_produzida}
    if requisicao.observacoes is not None:
        dados_atualizacao["observacoes"] = requisicao.observacoes

    alteracoes = []
    if existente["quantidade_produzida"] != requisicao.quantidade_produzida:
        alteracoes.append(
            {
                "campo": "quantidade_produzida",
                "valor_anterior": existente["quantidade_produzida"],
                "valor_novo": requisicao.quantidade_produzida,
            }
        )
    if (
        requisicao.observacoes is not None
        and existente.get("observacoes") != requisicao.observacoes
    ):
        alteracoes.append(
            {
                "campo": "observacoes",
                "valor_anterior": existente.get("observacoes"),
                "valor_novo": requisicao.observacoes,
            }
        )
    if not alteracoes:
        return None

    client.table("itens_producao").update(to_db_payload(dados_atualizacao)).eq(
        "id",
        existente["id"],
    ).execute()
    return {
        "tipo": "PRODUCAO_CORRIGIDA",
        "produto_id": existente["produto_id"],
        "produto": existente["nome_produto_no_momento"],
        "item_producao_id": existente["id"],
        "alteracoes": alteracoes,
    }


def _adicionar_producao_em_correcao(
    client: Client,
    dia_de_venda: dict,
    requisicao: RequisicaoCorrigirProducaoDiaFechado,
    *,
    usuario_id: UUID | str | None = None,
) -> dict:
    snapshot = produtos_public.buscar_snapshot_do_produto(
        requisicao.produto_id,
        date.fromisoformat(dia_de_venda["data_venda"]),
        usuario_id=usuario_id,
    )
    produto = snapshot["produto"]
    preco = snapshot["preco"]
    dados_item = to_db_payload(
        {
            "dia_de_venda_id": dia_de_venda["id"],
            "produto_id": requisicao.produto_id,
            "nome_produto_no_momento": produto["nome"],
            "url_imagem_produto_no_momento": produto.get("url_imagem_principal"),
            "versao_preco_id": preco["id"],
            "preco_venda_unitario_no_momento": preco["preco_venda"],
            "preco_custo_unitario_no_momento": preco["preco_custo"],
            "quantidade_produzida": requisicao.quantidade_produzida,
            "observacoes": requisicao.observacoes,
        }
    )
    item = client.table("itens_producao").insert(dados_item).execute().data[0]
    return {
        "tipo": "PRODUCAO_ADICIONADA",
        "produto_id": item["produto_id"],
        "produto": item["nome_produto_no_momento"],
        "item_producao_id": item["id"],
        "alteracoes": [
            {
                "campo": "quantidade_produzida",
                "valor_anterior": None,
                "valor_novo": item["quantidade_produzida"],
            }
        ],
    }


def _corrigir_item_venda_em_dia_fechado(
    client: Client,
    dia_de_venda: dict,
    requisicao: RequisicaoCorrigirItemVendaDiaFechado,
) -> dict | None:
    item = first_or_none(
        client.table("itens_venda")
        .select("*")
        .eq("id", str(requisicao.item_venda_id))
        .limit(1)
        .execute()
        .data
    )
    if not item:
        raise NotFoundError("Item de venda", str(requisicao.item_venda_id))
    if item["dia_de_venda_id"] != dia_de_venda["id"]:
        raise BadRequestError(
            "O item de venda informado nao pertence ao dia fechado.",
            {
                "item_venda_id": str(requisicao.item_venda_id),
                "dia_de_venda_id": dia_de_venda["id"],
            },
        )
    if item["quantidade"] == requisicao.quantidade:
        return None

    preco_venda = Decimal(str(item["preco_venda_unitario_no_momento"]))
    preco_custo = Decimal(str(item["preco_custo_unitario_no_momento"]))
    valor_total_venda = preco_venda * requisicao.quantidade
    valor_total_custo = preco_custo * requisicao.quantidade
    item_atualizado = (
        client.table("itens_venda")
        .update(
            to_db_payload(
                {
                    "quantidade": requisicao.quantidade,
                    "valor_total_venda": valor_total_venda,
                    "valor_total_custo": valor_total_custo,
                }
            )
        )
        .eq("id", str(requisicao.item_venda_id))
        .execute()
        .data[0]
    )
    return {
        "tipo": "ITEM_VENDA_CORRIGIDO",
        "venda_id": item["venda_id"],
        "item_venda_id": item["id"],
        "produto_id": item["produto_id"],
        "produto": item["nome_produto_no_momento"],
        "alteracoes": [
            {
                "campo": "quantidade",
                "valor_anterior": item["quantidade"],
                "valor_novo": item_atualizado["quantidade"],
            },
            {
                "campo": "valor_total_venda",
                "valor_anterior": item["valor_total_venda"],
                "valor_novo": item_atualizado["valor_total_venda"],
            },
        ],
    }


def _registrar_venda_retroativa_em_dia_fechado(
    dia_de_venda: dict,
    requisicao: RequisicaoVendaRetroativaDiaFechado,
) -> dict:
    from app.modules.vendas import servico as servico_de_vendas
    from app.modules.vendas.esquemas import RequisicaoItemVendido, RequisicaoRegistrarVenda

    venda = servico_de_vendas.registrar_venda(
        RequisicaoRegistrarVenda(
            dia_de_venda_id=UUID(dia_de_venda["id"]),
            itens=[
                RequisicaoItemVendido(produto_id=item.produto_id, quantidade=item.quantidade)
                for item in requisicao.itens
            ],
            tipo_entrada="manual",
            texto_original=requisicao.texto_original,
            observacoes=requisicao.observacoes,
            ocorrido_em=requisicao.ocorrido_em,
        ),
        permitir_dia_fechado=True,
        detalhes_evento={"origem": "correcao_dia_fechado"},
    )
    return {
        "tipo": "VENDA_ADICIONADA",
        "venda_id": venda["id"],
        "alteracoes": [
            {
                "campo": "venda",
                "valor_anterior": None,
                "valor_novo": {
                    "venda_id": venda["id"],
                    "itens": venda["itens"],
                    "ocorrido_em": venda["ocorrido_em"],
                },
            }
        ],
    }


def _cancelar_venda_em_correcao(
    dia_de_venda: dict,
    venda_id: UUID,
    motivo: str | None,
) -> dict | None:
    from app.modules.vendas import servico as servico_de_vendas
    from app.modules.vendas.esquemas import RequisicaoCancelarVenda

    venda_antes = servico_de_vendas.buscar_venda(venda_id)
    if venda_antes["dia_de_venda_id"] != dia_de_venda["id"]:
        raise BadRequestError(
            "A venda informada nao pertence ao dia fechado.",
            {"venda_id": str(venda_id), "dia_de_venda_id": dia_de_venda["id"]},
        )
    if venda_antes["situacao"] == "cancelada":
        return None

    venda_cancelada = servico_de_vendas.cancelar_venda(
        venda_id,
        RequisicaoCancelarVenda(motivo=motivo),
    )
    return {
        "tipo": "VENDA_CANCELADA",
        "venda_id": venda_cancelada["id"],
        "alteracoes": [
            {
                "campo": "situacao",
                "valor_anterior": venda_antes["situacao"],
                "valor_novo": venda_cancelada["situacao"],
            },
            {
                "campo": "motivo_cancelamento",
                "valor_anterior": venda_antes.get("motivo_cancelamento"),
                "valor_novo": venda_cancelada.get("motivo_cancelamento"),
            },
        ],
    }
