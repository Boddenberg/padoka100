"""Adapter HTTP para o Supabase Auth (GoTrue).

Unico ponto do modulo que fala com a API /auth/v1 do Supabase.
"""

import httpx

from app.core.config import get_settings
from app.core.errors import AppError


def buscar_usuario_do_token(token: str) -> dict:
    """Valida o access token no Supabase Auth e devolve o usuario bruto."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_api_key:
        raise AppError(
            status_code=401,
            code="supabase_auth_unavailable",
            message="Autenticacao Supabase indisponivel.",
            details={"missing": ["SUPABASE_URL", "SUPABASE_KEY ou SUPABASE_SERVICE_ROLE_KEY"]},
        )

    response = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
        headers={
            "apikey": settings.supabase_api_key,
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )
    if response.status_code in {401, 403}:
        raise AppError(
            status_code=401,
            code="invalid_token",
            message="Sessao invalida ou expirada.",
            details={},
        )
    response.raise_for_status()
    return response.json()
