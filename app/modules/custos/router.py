from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.auth.dependencias import exigir_papel
from app.modules.custos import servico
from app.modules.custos.esquemas import (
    CalculoCustoProdutoSaida,
    CustoAdicionalSaida,
    InsumoSaida,
    ReceitaSaida,
    RequisicaoAtualizarInsumo,
    RequisicaoCriarCustoAdicional,
    RequisicaoCriarInsumo,
    RequisicaoCriarReceita,
)

router = APIRouter(
    prefix="/custos",
    tags=["custos"],
    dependencies=[Depends(exigir_papel("dono"))],
)


@router.get("/insumos", response_model=list[InsumoSaida])
def listar_insumos() -> list[dict]:
    return servico.listar_insumos()


@router.post("/insumos", response_model=InsumoSaida, status_code=201)
def criar_insumo(requisicao: RequisicaoCriarInsumo) -> dict:
    return servico.criar_insumo(requisicao)


@router.patch("/insumos/{insumo_id}", response_model=InsumoSaida)
def atualizar_insumo(insumo_id: UUID, requisicao: RequisicaoAtualizarInsumo) -> dict:
    return servico.atualizar_insumo(insumo_id, requisicao)


@router.get("/produtos/{produto_id}/receitas", response_model=list[ReceitaSaida])
def listar_receitas_do_produto(produto_id: UUID) -> list[dict]:
    return servico.listar_receitas_do_produto(produto_id)


@router.post("/produtos/{produto_id}/receitas", response_model=ReceitaSaida, status_code=201)
def criar_receita(produto_id: UUID, requisicao: RequisicaoCriarReceita) -> dict:
    return servico.criar_receita(produto_id, requisicao)


@router.post(
    "/produtos/{produto_id}/custos-adicionais",
    response_model=CustoAdicionalSaida,
    status_code=201,
)
def criar_custo_adicional(
    produto_id: UUID,
    requisicao: RequisicaoCriarCustoAdicional,
) -> dict:
    return servico.criar_custo_adicional(produto_id, requisicao)


@router.get("/produtos/{produto_id}/calculo", response_model=CalculoCustoProdutoSaida)
def calcular_custo_do_produto(
    produto_id: UUID,
    receita_id: Annotated[UUID | None, Query()] = None,
) -> dict:
    return servico.calcular_custo_do_produto(produto_id, receita_id=receita_id)
