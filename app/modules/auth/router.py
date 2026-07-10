from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile

from app.modules.admin.dependencias import exigir_admin_real
from app.modules.auth import servico
from app.modules.auth.dependencias import obter_sessao_autenticada
from app.modules.auth.esquemas import (
    RequisicaoAtualizarPapel,
    RequisicaoAtualizarPerfil,
    RequisicaoAtualizarPlano,
    RequisicaoLogin,
    RequisicaoRegistrarUsuario,
    RequisicaoTrocarSenha,
    RespostaLogin,
    UsuarioSaida,
)

router = APIRouter(tags=["auth"])
SessaoAtual = Annotated[dict, Depends(obter_sessao_autenticada)]
AdminReal = Annotated[dict, Depends(exigir_admin_real)]


@router.post("/auth/registrar", response_model=UsuarioSaida, status_code=201)
def registrar_usuario(requisicao: RequisicaoRegistrarUsuario) -> dict:
    return servico.registrar_usuario(requisicao)


@router.post("/auth/login", response_model=RespostaLogin)
def login(requisicao: RequisicaoLogin) -> dict:
    return servico.login(requisicao)


@router.post("/auth/logout")
def logout(sessao: SessaoAtual) -> dict:
    if sessao["via_api_key"] or not sessao.get("sessao_id"):
        return {"sucesso": True}
    return servico.logout(sessao["sessao_id"])


@router.post("/auth/trocar-senha")
def trocar_senha(
    requisicao: RequisicaoTrocarSenha,
    sessao: SessaoAtual,
) -> dict:
    return servico.trocar_senha(sessao["usuario"]["id"], requisicao)


@router.get("/auth/usuarios", response_model=list[UsuarioSaida])
def listar_usuarios(_: AdminReal) -> list[dict]:
    return servico.listar_usuarios()


@router.patch("/auth/usuarios/{usuario_id}/papel", response_model=UsuarioSaida)
def atualizar_papel_usuario(
    usuario_id: UUID,
    requisicao: RequisicaoAtualizarPapel,
    _: AdminReal,
) -> dict:
    return servico.atualizar_papel_usuario(usuario_id, requisicao)


@router.patch("/auth/usuarios/{usuario_id}/plano", response_model=UsuarioSaida)
def atualizar_plano_usuario(
    usuario_id: UUID,
    requisicao: RequisicaoAtualizarPlano,
    _: AdminReal,
) -> dict:
    return servico.atualizar_plano_usuario(usuario_id, requisicao)


@router.get("/perfil/me", response_model=UsuarioSaida)
def buscar_meu_perfil(sessao: SessaoAtual) -> dict:
    return sessao["usuario"]


@router.patch("/perfil/me", response_model=UsuarioSaida)
def atualizar_meu_perfil(
    requisicao: RequisicaoAtualizarPerfil,
    sessao: SessaoAtual,
) -> dict:
    return servico.atualizar_perfil(sessao["usuario"]["id"], requisicao)


@router.post("/perfil/me/foto", response_model=UsuarioSaida)
async def atualizar_foto_do_perfil(
    file: Annotated[UploadFile, File()],
    sessao: SessaoAtual,
) -> dict:
    return await servico.atualizar_foto_perfil(sessao["usuario"]["id"], file)
