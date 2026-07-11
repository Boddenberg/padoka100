"""Conta nova com estado vazio, sessao anonima e autorizacao por plano."""

from tests.integration.conftest import API_KEY_DE_TESTE, promover_plano, registrar_e_logar


def test_conta_nova_recebe_estados_vazios_sem_erro(client):
    conta = registrar_e_logar(client, "nova@padoka.test", "Conta Nova")

    assert client.get("/api/v1/produtos", headers=conta["headers"]).json() == []
    assert client.get("/api/v1/locais", headers=conta["headers"]).json() == []
    assert client.get("/api/v1/dias-de-venda", headers=conta["headers"]).json() == []

    # Sem dia aberto: erro controlado 404, nao 500.
    atual = client.get("/api/v1/dias-de-venda/atual", headers=conta["headers"])
    assert atual.status_code == 404
    assert atual.json()["error"]["code"] == "not_found"


def test_rotas_protegidas_rejeitam_sessao_anonima(client):
    registrar_e_logar(client, "dona@padoka.test", "Dona")

    resposta = client.get("/api/v1/produtos", headers={"Authorization": "Bearer "})
    assert resposta.status_code == 401

    sem_header = client.get(
        "/api/v1/produtos",
        headers={"X-API-Key": "chave-errada"},
    )
    assert sem_header.status_code == 401


def test_token_invalido_recebe_erro_controlado(client):
    registrar_e_logar(client, "dona@padoka.test", "Dona")

    resposta = client.get(
        "/api/v1/produtos",
        headers={"Authorization": "Bearer token-que-nao-existe"},
    )
    assert resposta.status_code in {401, 503}


def test_plano_basico_nao_acessa_relatorios_avancados(client):
    conta = registrar_e_logar(client, "dona@padoka.test", "Dona")

    resposta = client.get(
        "/api/v1/relatorios/periodo",
        params={"data_inicio": "2026-07-01", "data_fim": "2026-07-05"},
        headers=conta["headers"],
    )
    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "feature_not_available"


def test_promocao_de_plano_via_api_key_libera_feature(client):
    conta = registrar_e_logar(client, "tester@padoka.test", "Tester")
    promover_plano(client, conta["usuario"]["id"], "analitico")

    resposta = client.get(
        "/api/v1/relatorios/periodo",
        params={"data_inicio": "2026-07-01", "data_fim": "2026-07-05"},
        headers=conta["headers"],
    )
    assert resposta.status_code == 200
    assert resposta.json()["faturamento_bruto"] == "0"


def test_usuario_comum_nao_promove_o_proprio_plano(client):
    conta = registrar_e_logar(client, "esperta@padoka.test", "Esperta")

    resposta = client.patch(
        f"/api/v1/auth/usuarios/{conta['usuario']['id']}/plano",
        json={"plano": "admin"},
        headers=conta["headers"],
    )
    assert resposta.status_code == 403


def test_logout_revoga_a_sessao(client):
    conta = registrar_e_logar(client, "sai@padoka.test", "Sai")

    logout = client.post("/api/v1/auth/logout", headers=conta["headers"])
    assert logout.status_code == 200

    depois = client.get("/api/v1/produtos", headers=conta["headers"])
    assert depois.status_code in {401, 503}


def test_perfil_me_rejeita_sessao_de_servico(client):
    registrar_e_logar(client, "dona@padoka.test", "Dona")

    resposta = client.get("/api/v1/perfil/me", headers={"X-API-Key": API_KEY_DE_TESTE})
    assert resposta.status_code == 403
