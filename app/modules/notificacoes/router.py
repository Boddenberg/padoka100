from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.modules.notificacoes import servico
from app.modules.notificacoes.esquemas import (
    NotificacaoSaida,
    RequisicaoAtualizarNotificacao,
    RequisicaoCriarNotificacao,
)

router = APIRouter(tags=["notificacoes"])

USUARIO_SISTEMA_SEM_AUTH = {
    "id": None,
    "email": "sem-auth@padoka.local",
    "nome": "Sem autenticacao",
    "papel": "dono",
    "situacao": "ativo",
}


@router.get("/notificacoes", response_model=list[NotificacaoSaida])
def listar_notificacoes_publicas(
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict]:
    return servico.listar_notificacoes_publicas(limite=limite)


@router.get("/notificacoes/{notificacao_id}", response_model=NotificacaoSaida)
def buscar_notificacao_publica(notificacao_id: UUID) -> dict:
    return servico.buscar_notificacao_publica(notificacao_id)


@router.get("/admin/notificacoes", response_model=list[NotificacaoSaida])
def listar_notificacoes_admin(
    status: Annotated[
        str | None,
        Query(pattern="^(rascunho|publicada|arquivada)$"),
    ] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict]:
    return servico.listar_notificacoes_admin(status=status, limite=limite)


@router.post("/admin/notificacoes", response_model=NotificacaoSaida, status_code=201)
def criar_notificacao(
    requisicao: RequisicaoCriarNotificacao,
) -> dict:
    return servico.criar_notificacao(requisicao, USUARIO_SISTEMA_SEM_AUTH)


@router.patch("/admin/notificacoes/{notificacao_id}", response_model=NotificacaoSaida)
def atualizar_notificacao(
    notificacao_id: UUID,
    requisicao: RequisicaoAtualizarNotificacao,
) -> dict:
    return servico.atualizar_notificacao(notificacao_id, requisicao)


@router.post("/admin/notificacoes/{notificacao_id}/publicar", response_model=NotificacaoSaida)
def publicar_notificacao(notificacao_id: UUID) -> dict:
    return servico.publicar_notificacao(notificacao_id)


@router.post("/admin/notificacoes/{notificacao_id}/arquivar", response_model=NotificacaoSaida)
def arquivar_notificacao(notificacao_id: UUID) -> dict:
    return servico.arquivar_notificacao(notificacao_id)


@router.post("/admin/notificacoes/{notificacao_id}/midias", response_model=NotificacaoSaida)
async def anexar_upload(
    notificacao_id: UUID,
    file: Annotated[UploadFile, File()],
    descricao: Annotated[str | None, Form()] = None,
    texto_alternativo: Annotated[str | None, Form()] = None,
) -> dict:
    return await servico.anexar_upload(
        notificacao_id,
        file,
        descricao=descricao,
        texto_alternativo=texto_alternativo,
    )
