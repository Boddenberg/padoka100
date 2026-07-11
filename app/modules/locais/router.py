from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.auth.dependencias import exigir_capacidade
from app.modules.locais import servico
from app.modules.locais.esquemas import LocalSaida, RequisicaoAtualizarLocal, RequisicaoCriarLocal

router = APIRouter(prefix="/locais", tags=["locais"])
CatalogoLer = Annotated[dict, Depends(exigir_capacidade("catalogo.ler"))]
CatalogoEditar = Annotated[dict, Depends(exigir_capacidade("catalogo.editar"))]


@router.get("", response_model=list[LocalSaida])
def listar_locais(usuario: CatalogoLer, somente_ativos: bool = True) -> list[dict]:
    return servico.listar_locais(somente_ativos=somente_ativos, usuario_id=usuario["id"])


@router.post("", response_model=LocalSaida, status_code=201)
def criar_local(requisicao: RequisicaoCriarLocal, usuario: CatalogoEditar) -> dict:
    return servico.criar_local(requisicao, usuario_id=usuario["id"])


@router.get("/{local_id}", response_model=LocalSaida)
def buscar_local(local_id: UUID, usuario: CatalogoLer) -> dict:
    return servico.buscar_local(local_id, usuario_id=usuario["id"])


@router.patch("/{local_id}", response_model=LocalSaida)
def atualizar_local(
    local_id: UUID,
    requisicao: RequisicaoAtualizarLocal,
    usuario: CatalogoEditar,
) -> dict:
    return servico.atualizar_local(local_id, requisicao, usuario_id=usuario["id"])
