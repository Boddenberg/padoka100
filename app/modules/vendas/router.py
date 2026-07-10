from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.auth.dependencias import exigir_capacidade
from app.modules.vendas import servico
from app.modules.vendas.esquemas import (
    RequisicaoCancelarVenda,
    RequisicaoRegistrarVenda,
    VendaSaida,
)

router = APIRouter(prefix="/vendas", tags=["vendas"])
VendasOperar = Annotated[dict, Depends(exigir_capacidade("vendas.operar"))]


@router.post("", response_model=VendaSaida, status_code=201)
def registrar_venda(requisicao: RequisicaoRegistrarVenda, _: VendasOperar = None) -> dict:
    return servico.registrar_venda(requisicao)


@router.get("/por-dia/{dia_de_venda_id}", response_model=list[VendaSaida])
def listar_vendas(dia_de_venda_id: UUID, _: VendasOperar = None) -> list[dict]:
    return servico.listar_vendas(dia_de_venda_id)


@router.get("/{venda_id}", response_model=VendaSaida)
def buscar_venda(venda_id: UUID, _: VendasOperar = None) -> dict:
    return servico.buscar_venda(venda_id)


@router.post("/{venda_id}/cancelar", response_model=VendaSaida)
def cancelar_venda(
    venda_id: UUID,
    requisicao: RequisicaoCancelarVenda,
    _: VendasOperar = None,
) -> dict:
    return servico.cancelar_venda(venda_id, requisicao)
