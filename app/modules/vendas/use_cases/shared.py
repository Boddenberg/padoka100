from collections import defaultdict
from uuid import UUID

from app.modules.vendas.adapters.supabase_repository import (
    DisponibilidadeVendaRepository,
    ItemVendaRepository,
    VendaRepository,
)
from app.modules.vendas.domain.availability import (
    calcular_quantidade_disponivel,
    calcular_quantidade_vendida,
    esgotou_com_a_venda,
)
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo


def anexar_itens_as_vendas(
    item_repository: ItemVendaRepository,
    vendas: list[dict],
) -> list[dict]:
    return item_repository.anexar_itens(vendas)


def registrar_eventos_de_esgotamento(
    venda_repository: VendaRepository,
    item_repository: ItemVendaRepository,
    disponibilidade_repository: DisponibilidadeVendaRepository,
    dia_de_venda: dict,
    itens_vendidos: list[dict],
) -> None:
    itens_por_produto = defaultdict(lambda: {"quantidade": 0, "produto": None})
    for item in itens_vendidos:
        produto_id = item["produto_id"]
        itens_por_produto[produto_id]["quantidade"] += item["quantidade"]
        itens_por_produto[produto_id]["produto"] = item

    for produto_id, resumo_item in itens_por_produto.items():
        quantidade_disponivel = calcular_quantidade_disponivel_do_produto(
            disponibilidade_repository,
            dia_de_venda["id"],
            produto_id,
        )
        quantidade_vendida = calcular_quantidade_vendida_ativa_do_produto(
            venda_repository,
            item_repository,
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
            venda_repository.client,
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


def calcular_quantidade_disponivel_do_produto(
    repository: DisponibilidadeVendaRepository,
    dia_de_venda_id: UUID | str,
    produto_id: UUID | str,
) -> int:
    return calcular_quantidade_disponivel(
        repository.listar_itens_producao(dia_de_venda_id, produto_id),
        repository.listar_decisoes_sobra(dia_de_venda_id, produto_id),
    )


def calcular_quantidade_vendida_ativa_do_produto(
    venda_repository: VendaRepository,
    item_repository: ItemVendaRepository,
    dia_de_venda_id: UUID | str,
    produto_id: UUID | str,
) -> int:
    vendas_ativas = venda_repository.listar_ativas_por_dia(dia_de_venda_id)
    venda_ids = [venda["id"] for venda in vendas_ativas]
    itens_venda = item_repository.listar_quantidades_por_produto(venda_ids, produto_id)
    return calcular_quantidade_vendida(itens_venda)
