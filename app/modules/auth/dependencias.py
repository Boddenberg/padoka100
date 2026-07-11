from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.auth import servico
from app.modules.auth.domain import capacidades


def obter_sessao_autenticada(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict:
    settings = get_settings()
    if settings.api_key and x_api_key and compare_digest(x_api_key, settings.api_key):
        return {
            "usuario": {
                "id": None,
                "email": "api-key@padoka.local",
                "nome": "API Key",
                "papel": "dono",
                "situacao": "ativo",
            },
            "sessao_id": None,
            "via_api_key": True,
        }

    if not authorization or not authorization.lower().startswith("bearer "):
        return {
            "usuario": servico.usuario_sem_token(),
            "sessao_id": None,
            "via_api_key": False,
            "sem_token": True,
        }
    token = authorization.split(" ", 1)[1].strip()
    usuario, sessao = servico.buscar_usuario_por_token(token)
    return {"usuario": usuario, "sessao_id": sessao["id"], "via_api_key": False, "sem_token": False}


def obter_usuario_autenticado(
    sessao: Annotated[dict, Depends(obter_sessao_autenticada)],
) -> dict:
    return sessao["usuario"]


def exigir_sessao_de_usuario(
    sessao: Annotated[dict, Depends(obter_sessao_autenticada)],
) -> dict:
    if sessao.get("sem_token"):
        raise AppError(
            status_code=401,
            code="unauthorized",
            message="Informe uma sessao autenticada para acessar esta rota.",
        )
    if sessao.get("via_api_key"):
        raise AppError(
            status_code=403,
            code="forbidden",
            message="Esta rota exige uma sessao de usuario, nao X-API-Key.",
        )
    return sessao


def obter_sessao_opcional(
    authorization: Annotated[str | None, Header()] = None,
) -> dict | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None

    token = authorization.split(" ", 1)[1].strip()
    usuario, sessao = servico.buscar_usuario_por_token(token)
    return {"usuario": usuario, "sessao_id": sessao["id"], "via_api_key": False, "sem_token": False}


def exigir_papel(*papeis: str):
    def dependencia(
        sessao: Annotated[dict, Depends(obter_sessao_autenticada)],
    ) -> dict:
        usuario = sessao["usuario"]
        if not servico.papel_atende(usuario, papeis):
            raise AppError(
                status_code=403,
                code="forbidden",
                message="Usuario nao tem permissao para esta acao.",
                details={"papeis_necessarios": list(papeis), "papel_atual": usuario.get("papel")},
            )
        return usuario

    return dependencia


def exigir_capacidade(capacidade: str):
    def dependencia(
        sessao: Annotated[dict, Depends(obter_sessao_autenticada)],
    ) -> dict:
        usuario = sessao["usuario"]
        if sessao.get("via_api_key"):
            return usuario
        if sessao.get("sem_token"):
            raise AppError(
                status_code=401,
                code="unauthorized",
                message="Informe uma sessao autenticada para acessar esta feature.",
                details={"capacidade_necessaria": capacidade},
            )
        if not capacidades.usuario_tem_capacidade(usuario, capacidade):
            raise AppError(
                status_code=403,
                code="feature_not_available",
                message="Seu plano nao libera esta feature.",
                details={
                    "capacidade_necessaria": capacidade,
                    "plano_atual": usuario.get("plano", "basico"),
                },
            )
        return usuario

    return dependencia
