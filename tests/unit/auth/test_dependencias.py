import pytest

from app.core.errors import AppError
from app.modules.auth.dependencias import exigir_sessao_de_usuario, obter_sessao_autenticada
from app.modules.auth.servico import USUARIO_SEM_TOKEN_ID


def test_sessao_sem_authorization_nao_carrega_usuario_real():
    sessao = obter_sessao_autenticada()

    assert sessao["sem_token"] is True
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
