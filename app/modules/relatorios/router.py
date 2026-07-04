from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query

from app.modules.relatorios import servico
from app.modules.relatorios.esquemas import ResumoDoDiaDeVenda, ResumoDoPeriodo

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


@router.get("/dias/{dia_de_venda_id}/resumo", response_model=ResumoDoDiaDeVenda)
def buscar_resumo_do_dia_de_venda(dia_de_venda_id: UUID) -> dict:
    return servico.buscar_resumo_do_dia_de_venda(dia_de_venda_id)


@router.get("/periodo", response_model=ResumoDoPeriodo)
def buscar_resumo_do_periodo(
    data_inicio: date = Query(...),
    data_fim: date = Query(...),
) -> dict:
    return servico.buscar_resumo_do_periodo(data_inicio, data_fim)
