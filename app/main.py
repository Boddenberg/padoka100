from secrets import compare_digest

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="API para controle visual de producao e vendas da Padoka 100.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    @app.middleware("http")
    async def require_api_key(request: Request, call_next):
        if (
            settings.api_key
            and request.method != "OPTIONS"
            and request.url.path.startswith(settings.api_prefix)
        ):
            header_api_key = request.headers.get("x-api-key", "")
            authorization = request.headers.get("authorization", "")
            tem_bearer = authorization.lower().startswith("bearer ")
            rota_publica_auth = request.url.path in {
                f"{settings.api_prefix}/auth/login",
                f"{settings.api_prefix}/auth/registrar",
            }
            if (
                not rota_publica_auth
                and not tem_bearer
                and not compare_digest(header_api_key, settings.api_key)
            ):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": "unauthorized",
                            "message": "Chave de API ausente ou invalida.",
                            "details": {"header": "X-API-Key"},
                        }
                    },
                )
        return await call_next(request)

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "app": settings.app_name,
            "environment": settings.app_env,
            "supabase_configured": settings.supabase_configured,
            "openai_text_configured": settings.openai_text_configured,
            "openai_audio_configured": settings.openai_audio_configured,
            "api_key_configured": settings.api_key_configured,
        }

    return app


app = create_app()
