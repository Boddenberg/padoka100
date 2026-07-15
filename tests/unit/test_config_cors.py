from app.core.config import Settings


def test_cors_inclui_frontend_de_producao() -> None:
    settings = Settings(
        cors_origins="http://localhost:5173",
        web_production_origin="https://padoka100-web-production.up.railway.app",
    )

    assert settings.cors_origins_resolved == [
        "http://localhost:5173",
        "https://padoka100-web-production.up.railway.app",
    ]


def test_cors_sem_configuracao_preserva_fallback_local() -> None:
    settings = Settings(cors_origins="")

    assert settings.cors_origins_resolved == ["*"]
