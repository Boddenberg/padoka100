from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.modules.auth.dependencias import exigir_capacidade, obter_sessao_opcional
from app.modules.notificacoes import servico
from app.modules.notificacoes.esquemas import (
    ContagemNotificacoesNaoLidasSaida,
    EstadoNotificacaoSaida,
    NotificacaoPublicaSaida,
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


SessaoOpcional = Annotated[dict | None, Depends(obter_sessao_opcional)]
NotificacoesLer = Annotated[dict, Depends(exigir_capacidade("notificacoes.ler"))]
NotificacoesAdmin = Annotated[dict, Depends(exigir_capacidade("notificacoes.admin"))]


@router.get("/notificacoes", response_model=list[NotificacaoPublicaSaida])
def listar_notificacoes_publicas(
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
    incluir_lidas: bool = True,
    incluir_ocultas: bool = False,
    sessao: SessaoOpcional = None,
    _: NotificacoesLer = None,
) -> list[dict]:
    return servico.listar_notificacoes_publicas(
        limite=limite,
        usuario_id=_usuario_id_da_sessao(sessao),
        incluir_lidas=incluir_lidas,
        incluir_ocultas=incluir_ocultas,
    )


@router.get(
    "/notificacoes/nao-lidas/contagem",
    response_model=ContagemNotificacoesNaoLidasSaida,
)
def contar_notificacoes_nao_lidas(
    sessao: SessaoOpcional = None,
    _: NotificacoesLer = None,
) -> dict:
    return servico.contar_notificacoes_nao_lidas(usuario_id=_usuario_id_da_sessao(sessao))


@router.get("/notificacoes/{notificacao_id}", response_model=NotificacaoPublicaSaida)
def buscar_notificacao_publica(
    notificacao_id: UUID,
    sessao: SessaoOpcional = None,
    _: NotificacoesLer = None,
) -> dict:
    return servico.buscar_notificacao_publica(
        notificacao_id,
        usuario_id=_usuario_id_da_sessao(sessao),
    )


@router.post("/notificacoes/{notificacao_id}/lida", response_model=EstadoNotificacaoSaida)
def marcar_notificacao_lida(
    notificacao_id: UUID,
    sessao: SessaoOpcional = None,
    _: NotificacoesLer = None,
) -> dict:
    return servico.marcar_notificacao_lida(
        notificacao_id,
        usuario_id=_usuario_id_da_sessao(sessao),
    )


@router.post("/notificacoes/{notificacao_id}/ler", response_model=EstadoNotificacaoSaida)
def marcar_notificacao_lida_alias(
    notificacao_id: UUID,
    sessao: SessaoOpcional = None,
    _: NotificacoesLer = None,
) -> dict:
    return servico.marcar_notificacao_lida(
        notificacao_id,
        usuario_id=_usuario_id_da_sessao(sessao),
    )


@router.post("/notificacoes/{notificacao_id}/nao-lida", response_model=EstadoNotificacaoSaida)
def desmarcar_notificacao_lida(
    notificacao_id: UUID,
    sessao: SessaoOpcional = None,
    _: NotificacoesLer = None,
) -> dict:
    return servico.desmarcar_notificacao_lida(
        notificacao_id,
        usuario_id=_usuario_id_da_sessao(sessao),
    )


@router.post("/notificacoes/{notificacao_id}/ocultar", response_model=EstadoNotificacaoSaida)
def ocultar_notificacao(
    notificacao_id: UUID,
    sessao: SessaoOpcional = None,
    _: NotificacoesLer = None,
) -> dict:
    return servico.ocultar_notificacao(
        notificacao_id,
        usuario_id=_usuario_id_da_sessao(sessao),
    )


@router.get("/admin/notificacoes", response_model=list[NotificacaoSaida])
def listar_notificacoes_admin(
    status: Annotated[
        str | None,
        Query(pattern="^(rascunho|publicada|arquivada)$"),
    ] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 100,
    _: NotificacoesAdmin = None,
) -> list[dict]:
    return servico.listar_notificacoes_admin(status=status, limite=limite)


@router.post("/admin/notificacoes", response_model=NotificacaoSaida, status_code=201)
def criar_notificacao(
    requisicao: RequisicaoCriarNotificacao,
    usuario: NotificacoesAdmin = None,
) -> dict:
    return servico.criar_notificacao(requisicao, usuario or USUARIO_SISTEMA_SEM_AUTH)


@router.patch("/admin/notificacoes/{notificacao_id}", response_model=NotificacaoSaida)
def atualizar_notificacao(
    notificacao_id: UUID,
    requisicao: RequisicaoAtualizarNotificacao,
    _: NotificacoesAdmin = None,
) -> dict:
    return servico.atualizar_notificacao(notificacao_id, requisicao)


@router.post("/admin/notificacoes/{notificacao_id}/publicar", response_model=NotificacaoSaida)
def publicar_notificacao(notificacao_id: UUID, _: NotificacoesAdmin = None) -> dict:
    return servico.publicar_notificacao(notificacao_id)


@router.post("/admin/notificacoes/{notificacao_id}/arquivar", response_model=NotificacaoSaida)
def arquivar_notificacao(notificacao_id: UUID, _: NotificacoesAdmin = None) -> dict:
    return servico.arquivar_notificacao(notificacao_id)


@router.post("/admin/notificacoes/{notificacao_id}/midias", response_model=NotificacaoSaida)
async def anexar_upload(
    notificacao_id: UUID,
    file: Annotated[UploadFile, File()],
    descricao: Annotated[str | None, Form()] = None,
    texto_alternativo: Annotated[str | None, Form()] = None,
    _: NotificacoesAdmin = None,
) -> dict:
    return await servico.anexar_upload(
        notificacao_id,
        file,
        descricao=descricao,
        texto_alternativo=texto_alternativo,
    )


def _usuario_id_da_sessao(sessao: dict | None) -> str | None:
    if not sessao or sessao.get("sem_token") or sessao.get("via_api_key"):
        return None
    usuario_id = sessao.get("usuario", {}).get("id")
    return str(usuario_id) if usuario_id else None
