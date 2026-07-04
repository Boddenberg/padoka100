from uuid import UUID

from fastapi import APIRouter

from app.modules.locais import servico
from app.modules.locais.esquemas import LocalSaida, RequisicaoAtualizarLocal, RequisicaoCriarLocal

router = APIRouter(prefix="/locais", tags=["locais"])


@router.get("", response_model=list[LocalSaida])
def listar_locais(somente_ativos: bool = True) -> list[dict]:
    return servico.listar_locais(somente_ativos=somente_ativos)


@router.post("", response_model=LocalSaida, status_code=201)
def criar_local(requisicao: RequisicaoCriarLocal) -> dict:
    return servico.criar_local(requisicao)


@router.get("/{local_id}", response_model=LocalSaida)
def buscar_local(local_id: UUID) -> dict:
    return servico.buscar_local(local_id)


@router.patch("/{local_id}", response_model=LocalSaida)
def atualizar_local(local_id: UUID, requisicao: RequisicaoAtualizarLocal) -> dict:
    return servico.atualizar_local(local_id, requisicao)
