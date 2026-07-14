from datetime import timedelta

from app.shared.datas import data_operacional_hoje
from tests.integration.conftest import API_KEY_DE_TESTE, registrar_e_logar

ADMIN_HEADERS = {"X-API-Key": API_KEY_DE_TESTE}


def test_seed_usa_produtos_do_usuario_e_registra_sobras_reais(client, banco):
    conta = registrar_e_logar(client, "massa@padoka.test", "Conta Massa")
    inicio = data_operacional_hoje() - timedelta(days=4)
    fim = inicio + timedelta(days=4)
    produto = client.post(
        "/api/v1/produtos",
        headers=conta["headers"],
        json={
            "nome": "Pao da casa",
            "preco_venda": "5.00",
            "preco_custo": "2.00",
            "vigente_desde": inicio.isoformat(),
        },
    )
    assert produto.status_code == 201, produto.text

    resposta = client.post(
        "/api/v1/admin/seed/vendas-fake",
        headers=ADMIN_HEADERS,
        json={
            "usuario_id": conta["usuario"]["id"],
            "data_inicio": inicio.isoformat(),
            "data_fim": fim.isoformat(),
            "produtos_por_dia_min": 1,
            "produtos_por_dia_max": 1,
            "quantidade_producao_min": 20,
            "quantidade_producao_max": 20,
            "vendas_por_dia_min": 3,
            "vendas_por_dia_max": 3,
            "quantidade_item_venda_min": 1,
            "quantidade_item_venda_max": 2,
            "probabilidade_reaproveitar_sobra": 1,
            "percentual_reaproveitamento_min": 0.5,
            "percentual_reaproveitamento_max": 0.5,
            "taxa_cancelamento": 0.5,
            "seed": 20260714,
        },
    )

    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert dados["usuario"]["id"] == conta["usuario"]["id"]
    assert dados["total_dias"] == 5
    assert {dia["cenario"] for dia in dados["dias"]} == {
        "normal",
        "alta_demanda",
        "baixa_demanda",
        "excesso_producao",
        "esgotamento",
    }
    assert dados["produtos_usados"] == [
        {"id": produto.json()["id"], "nome": "Pao da casa", "origem": "existente"}
    ]
    assert dados["total_unidades_sobra_reaproveitadas"] > 0
    assert dados["total_unidades_sobra_descartadas"] > 0
    assert dados["total_vendas_canceladas"] > 0

    dias = banco.tabelas["dias_de_venda"]
    assert len(dias) == 5
    assert {dia["usuario_id"] for dia in dias} == {conta["usuario"]["id"]}
    assert {dia["data_venda"] for dia in dias} == {
        (inicio + timedelta(days=offset)).isoformat() for offset in range(5)
    }
    decisoes = banco.tabelas["decisoes_sobra"]
    assert decisoes
    assert all(decisao["quantidade_sobra_origem"] > 0 for decisao in decisoes)
    assert any(decisao["quantidade_usada_hoje"] > 0 for decisao in decisoes)
    assert any(decisao["quantidade_nao_usada_hoje"] > 0 for decisao in decisoes)


def test_seed_por_email_pode_apenas_simular_fallback_sem_gravar(client, banco):
    registrar_e_logar(client, "sem-catalogo@padoka.test", "Sem Catalogo")
    data_alvo = data_operacional_hoje() - timedelta(days=1)

    resposta = client.post(
        "/api/v1/admin/seed/vendas-fake",
        headers=ADMIN_HEADERS,
        json={
            "usuario_email": "SEM-CATALOGO@PADOKA.TEST",
            "data_inicio": data_alvo.isoformat(),
            "data_fim": data_alvo.isoformat(),
            "somente_simular": True,
            "seed": 10,
        },
    )

    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert dados["somente_simulacao"] is True
    assert dados["usuario"]["email"] == "sem-catalogo@padoka.test"
    assert dados["produtos_usados"]
    assert {produto["origem"] for produto in dados["produtos_usados"]} == {"seed"}
    assert banco.tabelas.get("dias_de_venda", []) == []
    assert banco.tabelas.get("produtos", []) == []


def test_seed_rejeita_nome_de_usuario_ambiguo(client):
    registrar_e_logar(client, "um@padoka.test", "Padaria Centro")
    registrar_e_logar(client, "dois@padoka.test", "Padaria Centro")

    resposta = client.post(
        "/api/v1/admin/seed/vendas-fake",
        headers=ADMIN_HEADERS,
        json={"usuario_nome": "Padaria Centro", "somente_simular": True},
    )

    assert resposta.status_code == 400
    assert resposta.json()["error"]["details"]["usuarios_encontrados"]


def test_mesma_seed_reproduz_contagens_e_cenarios(client):
    conta = registrar_e_logar(client, "determinismo@padoka.test", "Determinismo")
    fim = data_operacional_hoje() - timedelta(days=1)
    inicio = fim - timedelta(days=5)
    payload = {
        "usuario_id": conta["usuario"]["id"],
        "data_inicio": inicio.isoformat(),
        "data_fim": fim.isoformat(),
        "somente_simular": True,
        "seed": 987654,
    }

    primeira = client.post(
        "/api/v1/admin/seed/vendas-fake",
        headers=ADMIN_HEADERS,
        json=payload,
    )
    segunda = client.post(
        "/api/v1/admin/seed/vendas-fake",
        headers=ADMIN_HEADERS,
        json=payload,
    )
    assert primeira.status_code == segunda.status_code == 201

    campos_totais = [
        "total_dias",
        "total_vendas",
        "total_itens_venda",
        "total_unidades_produzidas",
        "total_unidades_vendidas",
        "total_vendas_canceladas",
        "total_unidades_sobra_reaproveitadas",
        "total_unidades_sobra_descartadas",
        "total_unidades_sobrando",
        "produtos_usados",
    ]
    dados_primeira = primeira.json()
    dados_segunda = segunda.json()
    assert {campo: dados_primeira[campo] for campo in campos_totais} == {
        campo: dados_segunda[campo] for campo in campos_totais
    }
    campos_dia = [
        "data_venda",
        "produtos_produzidos",
        "vendas_criadas",
        "itens_venda_criados",
        "unidades_produzidas",
        "unidades_vendidas",
        "vendas_canceladas",
        "cenario",
        "unidades_sobra_recebidas",
        "unidades_sobra_reaproveitadas",
        "unidades_sobra_descartadas",
        "unidades_sobrando",
    ]
    assert [
        {campo: dia[campo] for campo in campos_dia} for dia in dados_primeira["dias"]
    ] == [{campo: dia[campo] for campo in campos_dia} for dia in dados_segunda["dias"]]
