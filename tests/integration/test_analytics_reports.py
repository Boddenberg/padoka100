from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.clock import hoje_operacional
from app.modules.analytics_reports import servico
from tests.integration.conftest import promover_plano, registrar_e_logar


def _sem_worker(monkeypatch):
    monkeypatch.setattr("app.modules.analytics_reports.worker.agendar", lambda _id: True)


def _semear_venda(banco, usuario_id: str, data_venda: str) -> None:
    dia_id = str(uuid4())
    produto_id = str(uuid4())
    venda_id = str(uuid4())
    agora = datetime.now(UTC).isoformat()
    banco.tabelas["dias_de_venda"] = [
        {
            "id": dia_id,
            "usuario_id": usuario_id,
            "data_venda": data_venda,
            "nome_local_no_momento": "Feira do bairro",
            "situacao": "fechado",
            "aberto_em": agora,
            "criado_em": agora,
            "atualizado_em": agora,
        }
    ]
    banco.tabelas["itens_producao"] = [
        {
            "id": str(uuid4()),
            "dia_de_venda_id": dia_id,
            "produto_id": produto_id,
            "nome_produto_no_momento": "Pao de queijo",
            "url_imagem_produto_no_momento": None,
            "quantidade_produzida": 20,
            "criado_em": agora,
            "atualizado_em": agora,
        }
    ]
    banco.tabelas["vendas"] = [
        {
            "id": venda_id,
            "usuario_id": usuario_id,
            "dia_de_venda_id": dia_id,
            "situacao": "ativa",
            "ocorrido_em": agora,
            "criado_em": agora,
            "atualizado_em": agora,
        }
    ]
    banco.tabelas["itens_venda"] = [
        {
            "id": str(uuid4()),
            "venda_id": venda_id,
            "dia_de_venda_id": dia_id,
            "produto_id": produto_id,
            "nome_produto_no_momento": "Pao de queijo",
            "quantidade": 15,
            "valor_total_venda": "75.00",
            "valor_total_custo": "30.00",
            "criado_em": agora,
        }
    ]


def test_fluxo_assincrono_notifica_exporta_e_aplica_cooldown(
    client, banco, monkeypatch
):
    _sem_worker(monkeypatch)
    conta = registrar_e_logar(client, "analytics@padoka.test", "Dona Analytics")
    promover_plano(client, conta["usuario"]["id"], "analitico")
    fim = hoje_operacional() - timedelta(days=1)
    inicio = fim - timedelta(days=6)
    _semear_venda(banco, conta["usuario"]["id"], fim.isoformat())

    solicitar = client.post(
        "/api/v1/analytics/relatorios",
        json={"data_inicio": inicio.isoformat(), "data_fim": fim.isoformat()},
        headers=conta["headers"],
    )
    assert solicitar.status_code == 202, solicitar.text
    relatorio_id = solicitar.json()["id"]
    assert solicitar.json()["status"] == "na_fila"

    servico.processar_relatorio(relatorio_id)
    pronto = client.get(
        f"/api/v1/analytics/relatorios/{relatorio_id}", headers=conta["headers"]
    )
    assert pronto.status_code == 200, pronto.text
    payload = pronto.json()
    assert payload["status"] == "pronto"
    assert payload["conteudo"]["indicadores"]["faturamento"] == 75
    assert payload["conteudo"]["indicadores"]["ticket_medio"] == 75
    assert payload["conteudo"]["produtos"][0]["nome"] == "Pao de queijo"

    feed = client.get("/api/v1/notificacoes/feed", headers=conta["headers"])
    assert feed.status_code == 200, feed.text
    aviso = feed.json()["itens"][0]
    assert aviso["metadados"]["relatorio_id"] == relatorio_id
    assert aviso["metadados"]["rota"] == f"/relatorio/{relatorio_id}"

    pdf = client.get(payload["url_exportacao"])
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    repetir = client.post(
        "/api/v1/analytics/relatorios",
        json={"data_inicio": inicio.isoformat(), "data_fim": fim.isoformat()},
        headers=conta["headers"],
    )
    assert repetir.status_code == 409
    assert repetir.json()["error"]["details"]["proxima_solicitacao_em"]


def test_plano_ia_recebe_leitura_estrategica_mesmo_sem_chave_openai(
    client, banco, monkeypatch
):
    _sem_worker(monkeypatch)
    conta = registrar_e_logar(client, "ia-report@padoka.test", "Dona IA")
    promover_plano(client, conta["usuario"]["id"], "ia")
    fim = hoje_operacional() - timedelta(days=1)
    inicio = fim - timedelta(days=6)

    resposta = client.post(
        "/api/v1/analytics/relatorios",
        json={"data_inicio": inicio.isoformat(), "data_fim": fim.isoformat()},
        headers=conta["headers"],
    )
    servico.processar_relatorio(resposta.json()["id"])
    linha = banco.tabelas["analytics_relatorios"][0]

    assert linha["tipo"] == "ia"
    assert linha["conteudo"]["ia"]["modelo"] == "analise-local"
    assert linha["conteudo"]["ia"]["acoes_recomendadas"]


def test_plano_basico_nao_pode_solicitar(client):
    conta = registrar_e_logar(client, "basico-report@padoka.test", "Conta Basica")
    hoje = hoje_operacional()
    resposta = client.post(
        "/api/v1/analytics/relatorios",
        json={"data_inicio": hoje.isoformat(), "data_fim": hoje.isoformat()},
        headers=conta["headers"],
    )
    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "feature_not_available"
