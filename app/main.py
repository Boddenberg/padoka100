from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.security import (
    api_key_obrigatoria,
    requisicao_tem_credencial_valida,
    resposta_api_key_invalida,
)


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
        if api_key_obrigatoria(request, settings) and not requisicao_tem_credencial_valida(
            request, settings
        ):
            return JSONResponse(status_code=401, content=resposta_api_key_invalida())
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
