"""Isolamento multiusuario ponta a ponta: usuario A nunca ve dados de B."""

from tests.integration.conftest import promover_plano, registrar_e_logar


def _criar_produto(client, headers, nome="Pao de Queijo", preco="10.00"):
    resposta = client.post(
        "/api/v1/produtos",
        json={"nome": nome, "preco_venda": preco, "preco_custo": "3.00"},
        headers=headers,
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _criar_dia_com_producao(client, headers, produto_id, quantidade=10):
    resposta = client.post(
        "/api/v1/dias-de-venda",
        json={
            "itens_producao": [
                {"produto_id": produto_id, "quantidade_produzida": quantidade}
            ]
        },
        headers=headers,
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def test_produtos_sao_isolados_entre_contas(client):
    usuaria_a = registrar_e_logar(client, "ana@padoka.test", "Ana")
    usuario_b = registrar_e_logar(client, "beto@padoka.test", "Beto")

    produto_a = _criar_produto(client, usuaria_a["headers"], nome="Pao Sovado")

    # B nao lista nem consulta o produto de A pelo id.
    lista_b = client.get("/api/v1/produtos", headers=usuario_b["headers"])
    assert lista_b.status_code == 200
    assert lista_b.json() == []

    consulta_b = client.get(
        f"/api/v1/produtos/{produto_a['id']}", headers=usuario_b["headers"]
    )
    assert consulta_b.status_code == 404

    # B nao edita o produto de A.
    edicao_b = client.patch(
        f"/api/v1/produtos/{produto_a['id']}",
        json={"nome": "Hackeado"},
        headers=usuario_b["headers"],
    )
    assert edicao_b.status_code == 404

    # Contas diferentes podem usar o mesmo nome de produto.
    produto_b = _criar_produto(client, usuario_b["headers"], nome="Pao Sovado")
    assert produto_b["nome"] == "Pao Sovado"

    # A continua vendo apenas o proprio produto.
    lista_a = client.get("/api/v1/produtos", headers=usuaria_a["headers"])
    assert [item["id"] for item in lista_a.json()] == [produto_a["id"]]


def test_locais_sao_isolados_entre_contas(client):
    usuaria_a = registrar_e_logar(client, "ana@padoka.test", "Ana")
    usuario_b = registrar_e_logar(client, "beto@padoka.test", "Beto")

    criacao = client.post(
        "/api/v1/locais", json={"nome": "Feira do Centro"}, headers=usuaria_a["headers"]
    )
    assert criacao.status_code == 201, criacao.text
    local_a = criacao.json()

    assert client.get("/api/v1/locais", headers=usuario_b["headers"]).json() == []
    assert (
        client.get(f"/api/v1/locais/{local_a['id']}", headers=usuario_b["headers"]).status_code
        == 404
    )


def test_dias_vendas_e_relatorios_sao_isolados(client):
    usuaria_a = registrar_e_logar(client, "ana@padoka.test", "Ana")
    usuario_b = registrar_e_logar(client, "beto@padoka.test", "Beto")

    produto_a = _criar_produto(client, usuaria_a["headers"])
    dia_a = _criar_dia_com_producao(client, usuaria_a["headers"], produto_a["id"])

    venda_a = client.post(
        "/api/v1/vendas",
        json={
            "dia_de_venda_id": dia_a["id"],
            "itens": [{"produto_id": produto_a["id"], "quantidade": 2}],
        },
        headers=usuaria_a["headers"],
    )
    assert venda_a.status_code == 201, venda_a.text
    venda_a = venda_a.json()

    # B nao ve o dia de A: listagem vazia, consulta/venda/relatorio 404.
    assert client.get("/api/v1/dias-de-venda", headers=usuario_b["headers"]).json() == []
    assert (
        client.get(
            f"/api/v1/dias-de-venda/{dia_a['id']}", headers=usuario_b["headers"]
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/vendas/por-dia/{dia_a['id']}", headers=usuario_b["headers"]
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/vendas/{venda_a['id']}", headers=usuario_b["headers"]
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/vendas/{venda_a['id']}/cancelar",
            json={"motivo": "tentativa indevida"},
            headers=usuario_b["headers"],
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/relatorios/dias/{dia_a['id']}/resumo", headers=usuario_b["headers"]
        ).status_code
        == 404
    )

    # B nao registra venda usando o dia de A.
    venda_cruzada = client.post(
        "/api/v1/vendas",
        json={
            "dia_de_venda_id": dia_a["id"],
            "itens": [{"produto_id": produto_a["id"], "quantidade": 1}],
        },
        headers=usuario_b["headers"],
    )
    assert venda_cruzada.status_code == 404

    # A segue com acesso normal aos proprios dados.
    resumo_a = client.get(
        f"/api/v1/relatorios/dias/{dia_a['id']}/resumo", headers=usuaria_a["headers"]
    )
    assert resumo_a.status_code == 200
    assert resumo_a.json()["total_vendido"] == 2


def test_producao_nao_aceita_produto_de_outra_conta(client):
    usuaria_a = registrar_e_logar(client, "ana@padoka.test", "Ana")
    usuario_b = registrar_e_logar(client, "beto@padoka.test", "Beto")

    produto_a = _criar_produto(client, usuaria_a["headers"])
    produto_b = _criar_produto(client, usuario_b["headers"], nome="Broa")
    dia_b = _criar_dia_com_producao(client, usuario_b["headers"], produto_b["id"])

    resposta = client.post(
        f"/api/v1/dias-de-venda/{dia_b['id']}/itens-producao",
        json={"produto_id": produto_a["id"], "quantidade_produzida": 5},
        headers=usuario_b["headers"],
    )
    assert resposta.status_code == 404


def test_historico_e_isolado_por_conta(client):
    usuaria_a = registrar_e_logar(client, "ana@padoka.test", "Ana")
    usuario_b = registrar_e_logar(client, "beto@padoka.test", "Beto")
    promover_plano(client, usuaria_a["usuario"]["id"], "analitico")
    promover_plano(client, usuario_b["usuario"]["id"], "analitico")

    _criar_produto(client, usuaria_a["headers"])

    eventos_a = client.get(
        "/api/v1/historico/linha-do-tempo", headers=usuaria_a["headers"]
    ).json()
    eventos_b = client.get(
        "/api/v1/historico/linha-do-tempo", headers=usuario_b["headers"]
    ).json()
    assert len(eventos_a) >= 1
    assert eventos_b == []


def test_correcao_de_dia_fechado_registra_autor_da_sessao(client):
    usuaria_a = registrar_e_logar(client, "ana@padoka.test", "Ana")
    produto_a = _criar_produto(client, usuaria_a["headers"])
    dia_a = _criar_dia_com_producao(client, usuaria_a["headers"], produto_a["id"])

    fechado = client.post(
        f"/api/v1/dias-de-venda/{dia_a['id']}/fechar",
        json={},
        headers=usuaria_a["headers"],
    )
    assert fechado.status_code == 200

    correcao = client.post(
        f"/api/v1/dias-de-venda/{dia_a['id']}/correcoes",
        json={
            "motivo": "ajuste de producao",
            # usuario_id enviado pelo cliente deve ser ignorado
            "usuario_id": "99999999-9999-9999-9999-999999999999",
            "producoes": [{"produto_id": produto_a["id"], "quantidade_produzida": 7}],
        },
        headers=usuaria_a["headers"],
    )
    assert correcao.status_code == 201, correcao.text
    assert correcao.json()["usuario_id"] == usuaria_a["usuario"]["id"]
