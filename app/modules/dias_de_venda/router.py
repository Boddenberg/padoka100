from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.modules.dias_de_venda import servico
from app.modules.dias_de_venda.esquemas import (
    DiaDeVendaSaida,
    IniciarDiaDeVendaSaida,
    ItemProducaoSaida,
    RequisicaoAtualizarDiaDeVenda,
    RequisicaoCorrigirDiaFechado,
    RequisicaoCriarDiaDeVenda,
    RequisicaoCriarItemProducao,
    RequisicaoFecharDiaDeVenda,
    RequisicaoIniciarDiaDeVenda,
)
from app.shared.esquemas import CorrecaoDiaFechadoSaida

router = APIRouter(prefix="/dias-de-venda", tags=["dias-de-venda"])


@router.get("", response_model=list[DiaDeVendaSaida])
def listar_dias_de_venda(
    data_inicio: Annotated[date | None, Query()] = None,
    data_fim: Annotated[date | None, Query()] = None,
    situacao: Annotated[str | None, Query(pattern="^(aberto|fechado)$")] = None,
) -> list[dict]:
    return servico.listar_dias_de_venda(
        data_inicio=data_inicio,
        data_fim=data_fim,
        situacao=situacao,
    )


@router.post("", response_model=DiaDeVendaSaida, status_code=201)
def criar_dia_de_venda(requisicao: RequisicaoCriarDiaDeVenda) -> dict:
    return servico.criar_dia_de_venda(requisicao)


@router.get("/atual", response_model=DiaDeVendaSaida)
def buscar_dia_de_venda_atual(
    data_venda: Annotated[date | None, Query()] = None,
) -> dict:
    return servico.buscar_dia_de_venda_atual(data_venda=data_venda)


@router.post("/iniciar-hoje", response_model=IniciarDiaDeVendaSaida)
def iniciar_dia_de_venda(requisicao: RequisicaoIniciarDiaDeVenda) -> dict:
    return servico.iniciar_dia_de_venda(requisicao)


@router.get("/{dia_de_venda_id}", response_model=DiaDeVendaSaida)
def buscar_dia_de_venda(dia_de_venda_id: UUID) -> dict:
    return servico.buscar_dia_de_venda(dia_de_venda_id)


@router.patch("/{dia_de_venda_id}", response_model=DiaDeVendaSaida)
def atualizar_dia_de_venda(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoAtualizarDiaDeVenda,
) -> dict:
    return servico.atualizar_dia_de_venda(dia_de_venda_id, requisicao)


@router.post("/{dia_de_venda_id}/itens-producao", response_model=ItemProducaoSaida)
def salvar_item_producao(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoCriarItemProducao,
) -> dict:
    return servico.salvar_item_producao(dia_de_venda_id, requisicao)


@router.post("/{dia_de_venda_id}/fechar", response_model=DiaDeVendaSaida)
def fechar_dia_de_venda(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoFecharDiaDeVenda,
) -> dict:
    return servico.fechar_dia_de_venda(dia_de_venda_id, requisicao)


@router.post(
    "/{dia_de_venda_id}/correcoes",
    response_model=CorrecaoDiaFechadoSaida,
    status_code=201,
)
def corrigir_dia_fechado(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoCorrigirDiaFechado,
) -> dict:
    return servico.corrigir_dia_fechado(dia_de_venda_id, requisicao)
