from datetime import date
from decimal import Decimal

from app.modules.analytics_reports.servico import _mesclar_dados_do_periodo


def test_mescla_blocos_compactos_sem_carregar_linhas_brutas():
    base = {
        "custoEstimado": "4.00",
        "lucroEstimado": "6.00",
        "quantidadeTotalProduzida": 8,
        "quantidadeTotalVendida": 5,
        "quantidadeTotalSobrando": 3,
        "quantidadeSobraAproveitada": 0,
        "quantidadeSobraDescartada": 0,
        "quantidadeVendas": 2,
        "correcoesRetroativas": [],
        "produtos": [
            {
                "produtoId": "produto-1",
                "produto": "Broa",
                "totalProduzido": 8,
                "totalVendido": 5,
                "totalSobrando": 3,
                "totalSobraAproveitada": 0,
                "totalSobraDescartada": 0,
                "faturamento": "10.00",
                "custoEstimado": "4.00",
                "lucroEstimado": "6.00",
                "diasEsgotado": 0,
            }
        ],
        "vendasPorHora": [{"hora": 9, "vendas": 2, "faturamento": 10}],
    }
    blocos = [
        {**base, "faturamentoTotal": "10.00", "dias": [{"data": "2026-07-01"}]},
        {**base, "faturamentoTotal": "10.00", "dias": [{"data": "2026-07-15"}]},
    ]

    dados = _mesclar_dados_do_periodo(
        blocos,
        data_inicio=date(2026, 7, 1),
        data_fim=date(2026, 7, 28),
    )

    assert dados["faturamentoTotal"] == Decimal("20.00")
    assert dados["quantidadeVendas"] == 4
    assert dados["produtos"][0]["totalVendido"] == 10
    assert dados["vendasPorHora"] == [{"hora": 9, "vendas": 4, "faturamento": 20.0}]
    assert [dia["data"] for dia in dados["dias"]] == ["2026-07-01", "2026-07-15"]
