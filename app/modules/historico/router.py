from uuid import UUID

from fastapi import APIRouter, Query

from app.modules.historico import servico
from app.shared.esquemas import EventoLinhaDoTempoSaida

router = APIRouter(prefix="/historico", tags=["historico"])


@router.get("/linha-do-tempo", response_model=list[EventoLinhaDoTempoSaida])
def listar_eventos_da_linha_do_tempo(
    dia_de_venda_id: UUID | None = Query(default=None),
    tipo_entidade: str | None = Query(default=None),
    entidade_id: UUID | None = Query(default=None),
    limite: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    return servico.listar_eventos_da_linha_do_tempo(
        dia_de_venda_id=dia_de_venda_id,
        tipo_entidade=tipo_entidade,
        entidade_id=entidade_id,
        limite=limite,
    )
