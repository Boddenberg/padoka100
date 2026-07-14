from datetime import UTC, datetime

from app.modules.analytics_reports.domain import montar_relatorio


def _dados(*, faturamento=1000, lucro=400, vendido=80, produzido=100, vendas=20):
    return {
        "periodo": {
            "inicio": "2026-07-01",
            "fim": "2026-07-07",
            "rotulo": "01/07/2026 a 07/07/2026",
        },
        "faturamentoTotal": faturamento,
        "custoEstimado": faturamento - lucro,
        "lucroEstimado": lucro,
        "quantidadeTotalProduzida": produzido,
        "quantidadeTotalVendida": vendido,
        "quantidadeTotalSobrando": produzido - vendido,
        "quantidadeSobraAproveitada": 3,
        "quantidadeSobraDescartada": 2,
        "quantidadeVendas": vendas,
        "produtos": [
            {
                "produtoId": "p1",
                "produto": "Pao de queijo",
                "totalProduzido": produzido,
                "totalVendido": vendido,
                "totalSobrando": produzido - vendido,
                "totalSobraAproveitada": 3,
                "totalSobraDescartada": 2,
                "faturamento": faturamento,
                "custoEstimado": faturamento - lucro,
                "lucroEstimado": lucro,
                "diasEsgotado": 1,
            }
        ],
        "dias": [
            {
                "data": "2026-07-01",
                "nomeLocal": "Feira",
                "faturamentoTotal": faturamento,
                "custoEstimado": faturamento - lucro,
                "lucroEstimado": lucro,
                "quantidadeTotalProduzida": produzido,
                "quantidadeTotalVendida": vendido,
                "quantidadeTotalSobrando": produzido - vendido,
                "quantidadeVendas": vendas,
            }
        ],
        "vendasPorHora": [{"hora": 9, "vendas": 10, "faturamento": 500}],
    }


def test_monta_indicadores_comparacoes_e_rankings():
    relatorio = montar_relatorio(
        atual=_dados(),
        anterior=_dados(faturamento=800, lucro=300, vendido=60, produzido=90, vendas=16),
        tipo="analytics",
        gerado_em=datetime(2026, 7, 8, tzinfo=UTC),
    )

    assert relatorio["indicadores"]["ticket_medio"] == 50
    assert relatorio["indicadores"]["eficiencia_venda_percentual"] == 80
    assert relatorio["comparacao"]["faturamento"]["variacao_percentual"] == 25
    assert relatorio["rankings"]["mais_vendidos"][0]["nome"] == "Pao de queijo"
    assert relatorio["produtos"][0]["participacao_percentual"] == 100
    assert relatorio["oportunidades"]
    assert relatorio["qualidade_dados"]["score"] > 0


def test_periodo_sem_dados_continua_gerando_relatorio_util():
    vazio = _dados(faturamento=0, lucro=0, vendido=0, produzido=0, vendas=0)
    vazio["dias"] = []
    vazio["produtos"] = []
    relatorio = montar_relatorio(
        atual=vazio,
        anterior=vazio,
        tipo="analytics",
        gerado_em=datetime(2026, 7, 8, tzinfo=UTC),
    )

    assert relatorio["indicadores"]["ticket_medio"] == 0
    assert relatorio["serie_diaria"] == []
    assert relatorio["alertas"][0]["nivel"] == "informativo"
