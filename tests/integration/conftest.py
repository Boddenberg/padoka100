"""Fixtures de integracao: app real + banco Supabase fake em memoria.

O cliente Supabase e um singleton com lru_cache; a fixture limpa os caches,
aponta as settings para valores fake e faz create_client devolver o banco em
memoria. Nenhum teste de integracao toca rede ou banco real.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.infra.supabase import client as supabase_client_module
from tests.integration.fake_supabase_db import BancoFake

API_KEY_DE_TESTE = "api-key-de-teste"


@pytest.fixture
def banco(monkeypatch) -> BancoFake:
    banco = BancoFake()
    monkeypatch.setenv("SUPABASE_URL", "http://fake.supabase.local")
    monkeypatch.setenv("SUPABASE_KEY", "fake-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-service-key")
    monkeypatch.setenv("API_KEY", API_KEY_DE_TESTE)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    supabase_client_module.get_supabase_client.cache_clear()
    monkeypatch.setattr(
        supabase_client_module,
        "create_client",
        lambda url, key: banco,
    )

    def rejeitar_token_desconhecido(_token: str) -> dict:
        from app.core.errors import AppError

        raise AppError(
            status_code=401,
            code="invalid_token",
            message="Sessao invalida ou expirada.",
            details={},
        )

    monkeypatch.setattr(
        "app.modules.auth.adapters.supabase_auth.buscar_usuario_do_token",
        rejeitar_token_desconhecido,
    )
    yield banco
    supabase_client_module.get_supabase_client.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def client(banco) -> TestClient:
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def registrar_e_logar(client: TestClient, email: str, nome: str) -> dict:
    """Cria a conta, faz login e devolve {'usuario', 'token', 'headers'}."""
    resposta = client.post(
        "/api/v1/auth/registrar",
        json={"email": email, "senha": "senha-super-secreta", "nome": nome},
    )
    assert resposta.status_code == 201, resposta.text
    usuario = resposta.json()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "senha": "senha-super-secreta"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {
        "usuario": usuario,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def promover_plano(client: TestClient, usuario_id: str, plano: str) -> None:
    """Promove a conta via rota administrativa autenticada por X-API-Key."""
    resposta = client.patch(
        f"/api/v1/auth/usuarios/{usuario_id}/plano",
        json={"plano": plano},
        headers={"X-API-Key": API_KEY_DE_TESTE},
    )
    assert resposta.status_code == 200, resposta.text
