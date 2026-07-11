from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.auth.dependencias import exigir_capacidade
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
VendasOperar = Annotated[dict, Depends(exigir_capacidade("vendas.operar"))]
RelatoriosBasicos = Annotated[dict, Depends(exigir_capacidade("relatorios.basicos"))]


@router.get("", response_model=list[DiaDeVendaSaida])
def listar_dias_de_venda(
    usuario: RelatoriosBasicos,
    data_inicio: Annotated[date | None, Query()] = None,
    data_fim: Annotated[date | None, Query()] = None,
    situacao: Annotated[str | None, Query(pattern="^(aberto|fechado)$")] = None,
) -> list[dict]:
    return servico.listar_dias_de_venda(
        data_inicio=data_inicio,
        data_fim=data_fim,
        situacao=situacao,
        usuario_id=usuario["id"],
    )


@router.post("", response_model=DiaDeVendaSaida, status_code=201)
def criar_dia_de_venda(requisicao: RequisicaoCriarDiaDeVenda, usuario: VendasOperar) -> dict:
    return servico.criar_dia_de_venda(requisicao, usuario_id=usuario["id"])


@router.get("/atual", response_model=DiaDeVendaSaida)
def buscar_dia_de_venda_atual(
    usuario: VendasOperar,
    data_venda: Annotated[date | None, Query()] = None,
) -> dict:
    return servico.buscar_dia_de_venda_atual(data_venda=data_venda, usuario_id=usuario["id"])


@router.post("/iniciar-hoje", response_model=IniciarDiaDeVendaSaida)
def iniciar_dia_de_venda(
    requisicao: RequisicaoIniciarDiaDeVenda,
    usuario: VendasOperar,
) -> dict:
    return servico.iniciar_dia_de_venda(requisicao, usuario_id=usuario["id"])


@router.get("/{dia_de_venda_id}", response_model=DiaDeVendaSaida)
def buscar_dia_de_venda(dia_de_venda_id: UUID, usuario: RelatoriosBasicos) -> dict:
    return servico.buscar_dia_de_venda(dia_de_venda_id, usuario_id=usuario["id"])


@router.patch("/{dia_de_venda_id}", response_model=DiaDeVendaSaida)
def atualizar_dia_de_venda(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoAtualizarDiaDeVenda,
    usuario: VendasOperar,
) -> dict:
    return servico.atualizar_dia_de_venda(dia_de_venda_id, requisicao, usuario_id=usuario["id"])


@router.post("/{dia_de_venda_id}/itens-producao", response_model=ItemProducaoSaida)
def salvar_item_producao(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoCriarItemProducao,
    usuario: VendasOperar,
) -> dict:
    return servico.salvar_item_producao(dia_de_venda_id, requisicao, usuario_id=usuario["id"])


@router.post("/{dia_de_venda_id}/fechar", response_model=DiaDeVendaSaida)
def fechar_dia_de_venda(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoFecharDiaDeVenda,
    usuario: VendasOperar,
) -> dict:
    return servico.fechar_dia_de_venda(dia_de_venda_id, requisicao, usuario_id=usuario["id"])


@router.post(
    "/{dia_de_venda_id}/correcoes",
    response_model=CorrecaoDiaFechadoSaida,
    status_code=201,
)
def corrigir_dia_fechado(
    dia_de_venda_id: UUID,
    requisicao: RequisicaoCorrigirDiaFechado,
    usuario: VendasOperar,
) -> dict:
    return servico.corrigir_dia_fechado(dia_de_venda_id, requisicao, usuario_id=usuario["id"])
