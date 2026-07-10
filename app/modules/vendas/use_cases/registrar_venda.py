from typing import Any
from uuid import UUID

from app.core.errors import BadRequestError
from app.modules.dias_de_venda import servico as servico_de_dias_de_venda
from app.modules.vendas.adapters.supabase_repository import (
    DisponibilidadeVendaRepository,
    ItemVendaRepository,
    VendaRepository,
)
from app.modules.vendas.domain.totals import montar_dados_item_vendido
from app.modules.vendas.esquemas import RequisicaoRegistrarVenda
from app.modules.vendas.use_cases.buscar_venda import buscar_venda
from app.modules.vendas.use_cases.shared import registrar_eventos_de_esgotamento
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo


def registrar_venda(
    requisicao: RequisicaoRegistrarVenda,
    *,
    permitir_dia_fechado: bool = False,
    detalhes_evento: dict[str, Any] | None = None,
    repository: VendaRepository | None = None,
) -> dict:
    venda_repo = repository or VendaRepository()
    item_repo = ItemVendaRepository(venda_repo.client)
    disponibilidade_repo = DisponibilidadeVendaRepository(venda_repo.client)
    dia_de_venda = servico_de_dias_de_venda.buscar_linha_dia_de_venda(
        venda_repo.client,
        requisicao.dia_de_venda_id,
    )
    if dia_de_venda["situacao"] == "fechado" and not permitir_dia_fechado:
        raise BadRequestError("Nao e possivel registrar venda em um dia fechado.")

    venda = venda_repo.inserir(
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
    linhas_itens = [
        montar_dados_item_vendido(venda["id"], dia_de_venda, item.produto_id, item.quantidade)
        for item in requisicao.itens
    ]
    item_repo.inserir_muitos(linhas_itens)

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
        venda_repo.client,
        tipo_evento="VENDA_REALIZADA",
        titulo="Venda registrada",
        tipo_entidade="venda",
        entidade_id=venda["id"],
        dia_de_venda_id=requisicao.dia_de_venda_id,
        detalhes=detalhes,
    )
    registrar_eventos_de_esgotamento(
        venda_repo,
        item_repo,
        disponibilidade_repo,
        dia_de_venda,
        linhas_itens,
    )
    return buscar_venda(UUID(venda["id"]), repository=venda_repo)
