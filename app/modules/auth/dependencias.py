from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.auth import servico


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
            "usuario": servico.buscar_usuario_padrao_sem_token(),
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
