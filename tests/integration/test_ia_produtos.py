from tests.integration.conftest import promover_plano, registrar_e_logar


def test_ia_cadastra_produto_com_confirmacao(client):
    conta = registrar_e_logar(client, "ia-produto@padoka.test", "IA Produto")
    promover_plano(client, conta["usuario"]["id"], "ia")

    interpretacao = client.post(
        "/api/v1/ia/interpretar-comando",
        json={"texto": "cadastre produto Broa de Milho por R$ 7,50"},
        headers=conta["headers"],
    )
    assert interpretacao.status_code == 200, interpretacao.text
    dados = interpretacao.json()
    assert dados["acao"] == "criar_produto"
    assert dados["precisa_confirmacao"] is True
    assert dados["dados_confirmacao"]["produto"]["nome"] == "Broa de Milho"
    assert dados["dados_confirmacao"]["produto"]["preco_venda"] == "7.50"

    confirmacao = client.post(
        f"/api/v1/ia/interacoes/{dados['interacao_ia_id']}/confirmar",
        headers=conta["headers"],
    )
    assert confirmacao.status_code == 200, confirmacao.text
    resultado = confirmacao.json()["resultado"]
    assert resultado["aplicado"] is True
    assert resultado["produto"]["nome"] == "Broa de Milho"
    assert resultado["produto"]["preco_atual"]["preco_venda"] == "7.50"
    assert resultado["produto"]["preco_atual"]["origem"] == "ia"
    assert resultado["produto"]["preco_atual"]["gerado_por_ia"] is True

    catalogo = client.get("/api/v1/produtos", headers=conta["headers"])
    assert catalogo.status_code == 200
    assert [produto["nome"] for produto in catalogo.json()] == ["Broa de Milho"]


def test_ia_pede_preco_antes_de_cadastrar_produto(client):
    conta = registrar_e_logar(client, "ia-sem-preco@padoka.test", "IA Sem Preco")
    promover_plano(client, conta["usuario"]["id"], "ia")

    resposta = client.post(
        "/api/v1/ia/interpretar-comando",
        json={"texto": "cadastre produto Pao de Batata"},
        headers=conta["headers"],
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["acao"] == "criar_produto"
    assert dados["precisa_confirmacao"] is False
    assert "preco de venda" in dados["mensagem_assistente"]
