from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.admin.dependencias import exigir_admin_real
from app.modules.rag import servico
from app.modules.rag.esquemas import DocumentoRagSaida, RequisicaoCriarDocumentoRag

router = APIRouter(prefix="/admin/rag", tags=["rag"])


@router.post("/documentos", response_model=DocumentoRagSaida, status_code=201)
def criar_documento(
    requisicao: RequisicaoCriarDocumentoRag,
    usuario: Annotated[dict, Depends(exigir_admin_real)],
) -> dict:
    return servico.criar_documento(requisicao, usuario)


@router.get("/documentos", response_model=list[DocumentoRagSaida])
def listar_documentos(
    _: Annotated[dict, Depends(exigir_admin_real)],
    status: Annotated[
        str | None,
        Query(pattern="^(pendente|indexado|arquivado)$"),
    ] = None,
    tipo: Annotated[str | None, Query(max_length=80)] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict]:
    return servico.listar_documentos(status=status, tipo=tipo, limite=limite)


@router.get("/documentos/{documento_id}", response_model=DocumentoRagSaida)
def buscar_documento(
    documento_id: UUID,
    _: Annotated[dict, Depends(exigir_admin_real)],
) -> dict:
    return servico.buscar_documento(documento_id)
