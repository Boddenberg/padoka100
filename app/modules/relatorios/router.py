from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.auth.dependencias import exigir_capacidade
from app.modules.relatorios import servico
from app.modules.relatorios.esquemas import (
    ResumoDoDiaDeVenda,
    ResumoDoPeriodo,
    ResumoDoPeriodoLeve,
    ResumoProdutoNoDia,
)

router = APIRouter(prefix="/relatorios", tags=["relatorios"])
RelatoriosBasicos = Annotated[dict, Depends(exigir_capacidade("relatorios.basicos"))]
RelatoriosAvancados = Annotated[dict, Depends(exigir_capacidade("relatorios.avancados"))]


@router.get("/dias/{dia_de_venda_id}/resumo", response_model=ResumoDoDiaDeVenda)
def buscar_resumo_do_dia_de_venda(
    dia_de_venda_id: UUID,
    usuario: RelatoriosBasicos,
    produto_id: Annotated[UUID | None, Query()] = None,
) -> dict:
    return servico.buscar_resumo_do_dia_de_venda(
        dia_de_venda_id,
        produto_id=produto_id,
        usuario_id=usuario["id"],
    )


@router.get("/dias/por-data/{data_venda}/resumo", response_model=ResumoDoDiaDeVenda)
def buscar_resumo_do_dia_por_data(
    data_venda: date,
    usuario: RelatoriosBasicos,
    produto_id: Annotated[UUID | None, Query()] = None,
) -> dict:
    return servico.buscar_resumo_do_dia_por_data(
        data_venda,
        produto_id=produto_id,
        usuario_id=usuario["id"],
    )


@router.get("/dias/{dia_de_venda_id}/produtos-venda", response_model=list[ResumoProdutoNoDia])
def buscar_produtos_da_venda_do_dia(
    dia_de_venda_id: UUID,
    usuario: RelatoriosBasicos,
) -> list[dict]:
    return servico.buscar_produtos_da_venda_do_dia(dia_de_venda_id, usuario_id=usuario["id"])


@router.get("/periodo", response_model=ResumoDoPeriodo)
def buscar_resumo_do_periodo(
    data_inicio: Annotated[date, Query()],
    data_fim: Annotated[date, Query()],
    usuario: RelatoriosAvancados,
    produto_id: Annotated[UUID | None, Query()] = None,
) -> dict:
    return servico.buscar_resumo_do_periodo(
        data_inicio,
        data_fim,
        produto_id=produto_id,
        usuario_id=usuario["id"],
    )


@router.get(
    "/periodo/resumo",
    response_model=ResumoDoPeriodoLeve,
    response_model_exclude_none=True,
)
def buscar_resumo_leve_do_periodo(
    data_inicio: Annotated[date, Query()],
    data_fim: Annotated[date, Query()],
    usuario: RelatoriosAvancados,
    comparar: Annotated[bool, Query()] = False,
    incluir_dias: Annotated[bool, Query()] = False,
) -> dict:
    return servico.buscar_resumo_leve_do_periodo(
        data_inicio,
        data_fim,
        comparar=comparar,
        incluir_dias=incluir_dias,
        usuario_id=usuario["id"],
    )
