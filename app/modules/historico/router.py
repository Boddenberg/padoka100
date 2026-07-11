from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.auth.dependencias import exigir_capacidade
from app.modules.historico import servico
from app.shared.esquemas import EventoLinhaDoTempoSaida

router = APIRouter(prefix="/historico", tags=["historico"])
HistoricoLer = Annotated[dict, Depends(exigir_capacidade("historico.ler"))]


@router.get("/linha-do-tempo", response_model=list[EventoLinhaDoTempoSaida])
def listar_eventos_da_linha_do_tempo(
    usuario: HistoricoLer,
    dia_de_venda_id: Annotated[UUID | None, Query()] = None,
    tipo_entidade: Annotated[str | None, Query()] = None,
    entidade_id: Annotated[UUID | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict]:
    return servico.listar_eventos_da_linha_do_tempo(
        dia_de_venda_id=dia_de_venda_id,
        tipo_entidade=tipo_entidade,
        entidade_id=entidade_id,
        limite=limite,
        usuario_id=usuario["id"],
    )
