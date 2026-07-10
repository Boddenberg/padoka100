from typing import Any
from uuid import UUID

from app.modules.vendas.esquemas import RequisicaoCancelarVenda, RequisicaoRegistrarVenda
from app.modules.vendas.use_cases.buscar_venda import buscar_venda as buscar_venda_use_case
from app.modules.vendas.use_cases.cancelar_venda import cancelar_venda as cancelar_venda_use_case
from app.modules.vendas.use_cases.listar_vendas import listar_vendas as listar_vendas_use_case
from app.modules.vendas.use_cases.registrar_venda import (
    registrar_venda as registrar_venda_use_case,
)


def registrar_venda(
    requisicao: RequisicaoRegistrarVenda,
    *,
    permitir_dia_fechado: bool = False,
    detalhes_evento: dict[str, Any] | None = None,
) -> dict:
    return registrar_venda_use_case(
        requisicao,
        permitir_dia_fechado=permitir_dia_fechado,
        detalhes_evento=detalhes_evento,
    )


def listar_vendas(dia_de_venda_id: UUID) -> list[dict]:
    return listar_vendas_use_case(dia_de_venda_id)


def buscar_venda(venda_id: UUID) -> dict:
    return buscar_venda_use_case(venda_id)


def cancelar_venda(venda_id: UUID, requisicao: RequisicaoCancelarVenda) -> dict:
    return cancelar_venda_use_case(venda_id, requisicao)
