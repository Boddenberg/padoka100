import logging
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


class MissingConfigurationError(AppError):
    def __init__(self, service: str, missing: list[str]) -> None:
        super().__init__(
            status_code=503,
            code="missing_configuration",
            message=f"{service} ainda nao foi configurado.",
            details={"missing": missing},
        )


class BadRequestError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            status_code=400,
            code="bad_request",
            message=message,
            details=details,
        )


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            status_code=404,
            code="not_found",
            message=f"{resource} nao encontrado.",
            details={"id": resource_id},
        )


class ConflictError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            status_code=409,
            code="conflict",
            message=message,
            details=details,
        )


class ExternalServiceError(AppError):
    """Falha de um servico externo (OpenAI, storage...).

    Devolve 502 com uma mensagem amigavel e, em `details`, a causa real
    (tipo e texto do erro) para diagnostico, em vez de um 500 seco.
    """

    def __init__(self, service: str, message: str, cause: Exception | None = None) -> None:
        details: dict[str, Any] = {"service": service}
        if cause is not None:
            details["type"] = type(cause).__name__
            details["detail"] = str(cause)[:800]
        super().__init__(
            status_code=502,
            code="external_service_error",
            message=message,
            details=details,
        )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(httpx.HTTPError)
    async def handle_http_error(_: Request, exc: httpx.HTTPError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "external_service_unavailable",
                    "message": "Nao foi possivel conectar a um servico externo.",
                    "details": {"type": type(exc).__name__},
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # Rede de seguranca: nenhum erro vira "500 seco" sem causa. Loga o
        # traceback completo e devolve o tipo/mensagem reais para diagnostico.
        logger.exception("Erro nao tratado")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Algo deu errado no servidor.",
                    "details": {"type": type(exc).__name__, "detail": str(exc)[:800]},
                }
            },
        )
