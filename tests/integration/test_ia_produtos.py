import json

from app.core.config import get_settings
from tests.integration.conftest import promover_plano, registrar_e_logar


class _RespostaOpenAIFake:
    def __init__(self, payload: dict) -> None:
        self.output_text = json.dumps(payload)


class _ResponsesOpenAIFake:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.chamadas = []

    def create(self, **kwargs):
        self.chamadas.append(kwargs)
        return _RespostaOpenAIFake(self.payload)


class _OpenAIFake:
    def __init__(self, payload: dict) -> None:
        self.responses = _ResponsesOpenAIFake(payload)


def _criar_produto(client, headers, nome="Pao de Queijo", preco="10.00"):
    resposta = client.post(
        "/api/v1/produtos",
        json={"nome": nome, "preco_venda": preco, "preco_custo": "3.00"},
        headers=headers,
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _criar_dia(client, headers):
    resposta = client.post("/api/v1/dias-de-venda", json={}, headers=headers)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


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


def test_ia_importa_cardapio_por_foto_e_cadastra_todos(monkeypatch, client):
    conta = registrar_e_logar(client, "ia-cardapio@padoka.test", "IA Cardapio")
    promover_plano(client, conta["usuario"]["id"], "ia")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "fake-vision-model")
    get_settings.cache_clear()

    payload = {
        "produtos": [
            {
                "nome": "Pao de Queijo",
                "descricao": None,
                "descricao_visual": None,
                "url_imagem_principal": None,
                "cor_botao": None,
                "ordem_exibicao": 1,
                "preco_venda": 5.5,
                "preco_custo": None,
                "vigente_desde": None,
            },
            {
                "nome": "Pao Sovado",
                "descricao": None,
                "descricao_visual": None,
                "url_imagem_principal": None,
                "cor_botao": None,
                "ordem_exibicao": 2,
                "preco_venda": 9,
                "preco_custo": None,
                "vigente_desde": None,
            },
        ],
        "itens_sem_preco": [],
        "avisos": [],
    }
    openai_fake = _OpenAIFake(payload)
    monkeypatch.setattr("app.modules.ia.servico.get_openai_client", lambda: openai_fake)

    interpretacao = client.post(
        "/api/v1/ia/produtos/importar-cardapio",
        files={"file": ("menu.jpg", b"imagem-fake", "image/jpeg")},
        data={"contexto": "Cardapio da banca do meu pai"},
        headers=conta["headers"],
    )
    assert interpretacao.status_code == 200, interpretacao.text
    dados = interpretacao.json()
    assert dados["acao"] == "criar_produtos"
    assert dados["precisa_confirmacao"] is True
    assert len(dados["dados_confirmacao"]["produtos"]) == 2
    assert dados["dados_confirmacao"]["url_imagem"].startswith("https://storage.fake.local/")
    assert openai_fake.responses.chamadas

    confirmacao = client.post(
        f"/api/v1/ia/interacoes/{dados['interacao_ia_id']}/confirmar",
        headers=conta["headers"],
    )
    assert confirmacao.status_code == 200, confirmacao.text
    resultado = confirmacao.json()["resultado"]
    assert resultado["aplicado"] is True
    assert resultado["quantidade"] == 2
    assert [produto["nome"] for produto in resultado["produtos"]] == [
        "Pao de Queijo",
        "Pao Sovado",
    ]

    catalogo = client.get("/api/v1/produtos", headers=conta["headers"])
    assert catalogo.status_code == 200
    assert [produto["nome"] for produto in catalogo.json()] == ["Pao de Queijo", "Pao Sovado"]


def test_ia_importa_producao_por_foto_e_salva_no_dia(monkeypatch, client):
    conta = registrar_e_logar(client, "ia-producao-foto@padoka.test", "IA Producao")
    promover_plano(client, conta["usuario"]["id"], "ia")
    produto = _criar_produto(client, conta["headers"], nome="Pao de Queijo")
    dia = _criar_dia(client, conta["headers"])
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "fake-vision-model")
    get_settings.cache_clear()

    payload = {
        "data_venda": None,
        "nome_local": None,
        "itens": [
            {
                "produto_id": produto["id"],
                "nome_produto": "Pao de Queijo",
                "quantidade": 24,
                "confianca": 0.92,
            }
        ],
        "itens_nao_identificados": [],
        "avisos": [],
    }
    monkeypatch.setattr("app.modules.ia.servico.get_openai_client", lambda: _OpenAIFake(payload))

    interpretacao = client.post(
        "/api/v1/ia/producao/importar-foto",
        files={"file": ("producao.jpg", b"imagem-fake", "image/jpeg")},
        data={
            "dia_de_venda_id": dia["id"],
            "contexto": "foto do quadro de producao de hoje",
        },
        headers=conta["headers"],
    )
    assert interpretacao.status_code == 200, interpretacao.text
    dados = interpretacao.json()
    assert dados["acao"] == "registrar_producao"
    assert dados["precisa_confirmacao"] is True
    assert dados["itens"][0]["quantidade"] == 24
    assert dados["dados_confirmacao"]["url_imagem"].startswith("https://storage.fake.local/")

    confirmacao = client.post(
        f"/api/v1/ia/interacoes/{dados['interacao_ia_id']}/confirmar",
        headers=conta["headers"],
    )
    assert confirmacao.status_code == 200, confirmacao.text
    resultado = confirmacao.json()["resultado"]
    assert resultado["aplicado"] is True
    assert resultado["itens_producao"][0]["quantidade_produzida"] == 24
