import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import AppError
from app.main import create_app
from app.modules.auth.dependencias import (
    USUARIO_API_KEY_ID,
    exigir_sessao_de_usuario,
    obter_sessao_autenticada,
)
from app.modules.auth.esquemas import UsuarioSaida
from app.modules.auth.servico import USUARIO_SEM_TOKEN_ID


def test_sessao_sem_authorization_nao_carrega_usuario_real():
    sessao = obter_sessao_autenticada()

    assert sessao["sem_token"] is True
    assert sessao["usuario"]["papel"] == "usuario"
    assert sessao["via_api_key"] is False
    assert sessao["usuario"]["id"] == USUARIO_SEM_TOKEN_ID
    assert sessao["usuario"]["email"] == "sem-token@padoka.local"


def test_rota_de_usuario_rejeita_sessao_sem_token():
    with pytest.raises(AppError) as exc_info:
        exigir_sessao_de_usuario(
            {
                "usuario": {"id": USUARIO_SEM_TOKEN_ID},
                "sessao_id": None,
                "via_api_key": False,
                "sem_token": True,
            }
        )

    assert exc_info.value.status_code == 401


def test_rota_de_usuario_rejeita_api_key_de_servico():
    with pytest.raises(AppError) as exc_info:
        exigir_sessao_de_usuario(
            {
                "usuario": {"id": None},
                "sessao_id": None,
                "via_api_key": True,
                "sem_token": False,
            }
        )

    assert exc_info.value.status_code == 403


def test_rota_de_usuario_aceita_bearer_validado():
    sessao = {
        "usuario": {"id": "11111111-1111-1111-1111-111111111111"},
        "sessao_id": None,
        "via_api_key": False,
        "sem_token": False,
    }

    assert exigir_sessao_de_usuario(sessao) is sessao


def test_sessao_via_api_key_monta_usuario_valido(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    get_settings.cache_clear()

    try:
        sessao = obter_sessao_autenticada(x_api_key="secret")
        usuario = UsuarioSaida.model_validate(sessao["usuario"])
    finally:
        get_settings.cache_clear()

    assert sessao["via_api_key"] is True
    assert str(usuario.id) == USUARIO_API_KEY_ID
    assert usuario.email == "api-key@padoka.local"
    assert usuario.plano == "admin"
    assert "admin.gerenciar" in usuario.capacidades


def test_perfil_me_com_api_key_rejeita_sessao_de_servico(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    get_settings.cache_clear()

    try:
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        resposta = client.get("/api/v1/perfil/me", headers={"x-api-key": "secret"})
    finally:
        get_settings.cache_clear()

    assert resposta.status_code == 403
