from typing import Annotated

from fastapi import Depends

from app.core.errors import AppError
from app.modules.auth.dependencias import obter_sessao_autenticada


def exigir_admin_real(
    sessao: Annotated[dict, Depends(obter_sessao_autenticada)],
) -> dict:
    usuario = sessao["usuario"]
    if sessao.get("via_api_key"):
        return usuario

    if sessao.get("sem_token"):
        raise AppError(
            status_code=401,
            code="unauthorized",
            message="Informe um token de administrador ou X-API-Key para esta rota.",
        )

    if usuario.get("papel") not in {"administrador", "dono"}:
        raise AppError(
            status_code=403,
            code="forbidden",
            message="Usuario nao tem permissao para esta acao.",
            details={"papeis_necessarios": ["administrador", "dono"]},
        )
    return usuario
