from types import SimpleNamespace

from app.core.config import Settings
from app.core.security import (
    api_key_obrigatoria,
    requisicao_tem_credencial_valida,
    rota_isenta_de_api_key,
)

PREFIXO = "/api/v1"
SETTINGS = Settings(api_key="secret", api_prefix=PREFIXO)


def _request(path: str, *, method: str = "GET", headers: dict | None = None):
    return SimpleNamespace(
        method=method,
        url=SimpleNamespace(path=path),
        headers=headers or {},
    )


def test_rota_isenta_reconhece_rotas_publicas():
    assert rota_isenta_de_api_key(f"{PREFIXO}/auth/login", PREFIXO)
    assert rota_isenta_de_api_key(f"{PREFIXO}/notificacoes", PREFIXO)
    assert rota_isenta_de_api_key(f"{PREFIXO}/notificacoes/123", PREFIXO)
    assert rota_isenta_de_api_key(f"{PREFIXO}/admin/notificacoes/1/ler", PREFIXO)


def test_rota_protegida_nao_e_isenta():
    assert not rota_isenta_de_api_key(f"{PREFIXO}/produtos", PREFIXO)
    assert not rota_isenta_de_api_key(f"{PREFIXO}/vendas", PREFIXO)


def test_api_key_obrigatoria_apenas_em_rotas_de_api():
    assert api_key_obrigatoria(_request(f"{PREFIXO}/produtos"), SETTINGS)
    assert not api_key_obrigatoria(_request(f"{PREFIXO}/produtos", method="OPTIONS"), SETTINGS)
    assert not api_key_obrigatoria(_request("/health"), SETTINGS)


def test_api_key_nao_obrigatoria_sem_key_configurada():
    sem_key = Settings(api_key="", api_prefix=PREFIXO)
    assert not api_key_obrigatoria(_request(f"{PREFIXO}/produtos"), sem_key)


def test_credencial_valida_via_rota_isenta():
    assert requisicao_tem_credencial_valida(_request(f"{PREFIXO}/auth/login"), SETTINGS)


def test_credencial_valida_via_bearer():
    req = _request(f"{PREFIXO}/produtos", headers={"authorization": "Bearer abc"})
    assert requisicao_tem_credencial_valida(req, SETTINGS)


def test_credencial_valida_via_api_key_correta():
    req = _request(f"{PREFIXO}/produtos", headers={"x-api-key": "secret"})
    assert requisicao_tem_credencial_valida(req, SETTINGS)


def test_credencial_invalida_sem_creds_em_rota_protegida():
    req = _request(f"{PREFIXO}/produtos", headers={"x-api-key": "errada"})
    assert not requisicao_tem_credencial_valida(req, SETTINGS)
