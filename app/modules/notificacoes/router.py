from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.modules.auth.dependencias import exigir_capacidade
from app.modules.notificacoes import servico
from app.modules.notificacoes.esquemas import (
    ContagemNotificacoesNaoLidasSaida,
    EstadoNotificacaoSaida,
    LimpezaNotificacoesSaida,
    NotificacaoPublicaSaida,
    NotificacaoSaida,
    RequisicaoAtualizarNotificacao,
    RequisicaoCriarNotificacao,
)

router = APIRouter(tags=["notificacoes"])

NotificacoesLer = Annotated[dict, Depends(exigir_capacidade("notificacoes.ler"))]
NotificacoesAdmin = Annotated[dict, Depends(exigir_capacidade("notificacoes.admin"))]


@router.get("/notificacoes", response_model=list[NotificacaoPublicaSaida])
def listar_notificacoes_publicas(
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
    incluir_lidas: bool = True,
    incluir_ocultas: bool = False,
    usuario: NotificacoesLer = None,
) -> list[dict]:
    return servico.listar_notificacoes_publicas(
        limite=limite,
        usuario=usuario,
        incluir_lidas=incluir_lidas,
        incluir_ocultas=incluir_ocultas,
    )


@router.get(
    "/notificacoes/nao-lidas/contagem",
    response_model=ContagemNotificacoesNaoLidasSaida,
)
def contar_notificacoes_nao_lidas(
    usuario: NotificacoesLer = None,
) -> dict:
    return servico.contar_notificacoes_nao_lidas(usuario=usuario)


@router.get("/notificacoes/{notificacao_id}", response_model=NotificacaoPublicaSaida)
def buscar_notificacao_publica(
    notificacao_id: UUID,
    usuario: NotificacoesLer = None,
) -> dict:
    return servico.buscar_notificacao_publica(
        notificacao_id,
        usuario=usuario,
    )


@router.post("/notificacoes/{notificacao_id}/lida", response_model=EstadoNotificacaoSaida)
def marcar_notificacao_lida(
    notificacao_id: UUID,
    usuario: NotificacoesLer = None,
) -> dict:
    return servico.marcar_notificacao_lida(
        notificacao_id,
        usuario=usuario,
    )


@router.post("/notificacoes/{notificacao_id}/ler", response_model=EstadoNotificacaoSaida)
def marcar_notificacao_lida_alias(
    notificacao_id: UUID,
    usuario: NotificacoesLer = None,
) -> dict:
    return servico.marcar_notificacao_lida(
        notificacao_id,
        usuario=usuario,
    )


@router.post("/notificacoes/{notificacao_id}/nao-lida", response_model=EstadoNotificacaoSaida)
def desmarcar_notificacao_lida(
    notificacao_id: UUID,
    usuario: NotificacoesLer = None,
) -> dict:
    return servico.desmarcar_notificacao_lida(
        notificacao_id,
        usuario=usuario,
    )


@router.post("/notificacoes/{notificacao_id}/ocultar", response_model=EstadoNotificacaoSaida)
def ocultar_notificacao(
    notificacao_id: UUID,
    usuario: NotificacoesLer = None,
) -> dict:
    return servico.ocultar_notificacao(
        notificacao_id,
        usuario=usuario,
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
    usuario: NotificacoesAdmin,
) -> dict:
    return servico.criar_notificacao(requisicao, usuario)


@router.delete(
    "/admin/notificacoes/expiradas",
    response_model=LimpezaNotificacoesSaida,
)
def limpar_notificacoes_expiradas(_: NotificacoesAdmin = None) -> dict:
    return servico.limpar_notificacoes_expiradas()


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


@router.delete("/admin/notificacoes/{notificacao_id}", status_code=204)
def excluir_notificacao(notificacao_id: UUID, _: NotificacoesAdmin = None) -> None:
    servico.excluir_notificacao(notificacao_id)


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
