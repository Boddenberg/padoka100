"""Regras de borda para a checagem global de API key.

O `main.py` monta o middleware; toda a decisao de "esta requisicao precisa de
API key e ela e valida?" vive aqui, isolada e testavel.
"""

from secrets import compare_digest

from fastapi import Request

from app.core.config import Settings

# Rotas publicas por design (relativas ao prefixo da API), isentas de API key.
_ROTAS_ISENTAS_EXATAS = (
    "/auth/login",
    "/auth/registrar",
    "/admin/seed/vendas-fake",
    "/notificacoes",
    "/admin/notificacoes",
)
_PREFIXOS_ISENTOS = (
    "/notificacoes/",
    "/admin/notificacoes/",
)


def rota_isenta_de_api_key(path: str, api_prefix: str) -> bool:
    rotas_exatas = {f"{api_prefix}{rota}" for rota in _ROTAS_ISENTAS_EXATAS}
    prefixos = tuple(f"{api_prefix}{prefixo}" for prefixo in _PREFIXOS_ISENTOS)
    return path in rotas_exatas or any(path.startswith(prefixo) for prefixo in prefixos)


def api_key_obrigatoria(request: Request, settings: Settings) -> bool:
    """A checagem so vale para requisicoes de API nao-preflight, com key configurada."""
    return bool(
        settings.api_key
        and request.method != "OPTIONS"
        and request.url.path.startswith(settings.api_prefix)
    )


def requisicao_tem_credencial_valida(request: Request, settings: Settings) -> bool:
    """Rota isenta, bearer token ou X-API-Key correta liberam a requisicao."""
    header_api_key = request.headers.get("x-api-key", "")
    authorization = request.headers.get("authorization", "")
    tem_bearer = authorization.lower().startswith("bearer ")
    return (
        rota_isenta_de_api_key(request.url.path, settings.api_prefix)
        or tem_bearer
        or compare_digest(header_api_key, settings.api_key)
    )


def resposta_api_key_invalida() -> dict:
    return {
        "error": {
            "code": "unauthorized",
            "message": "Chave de API ausente ou invalida.",
            "details": {"header": "X-API-Key"},
        }
    }
