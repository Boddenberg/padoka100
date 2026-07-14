from datetime import date

from app.infra.supabase.pagination import executar_paginado
from app.shared.periodos import dividir_periodo_em_blocos
from tests.integration.fake_supabase_db import BancoFake


def test_executar_paginado_ultrapassa_limite_padrao_do_postgrest():
    banco = BancoFake()
    banco.tabelas["linhas"] = [
        {"id": f"{indice:04d}", "valor": indice} for indice in range(1_205)
    ]

    linhas = executar_paginado(
        lambda: banco.table("linhas").select("id,valor").order("id")
    )

    assert len(linhas) == 1_205
    assert linhas[0]["valor"] == 0
    assert linhas[-1]["valor"] == 1_204


def test_periodo_longo_e_dividido_em_blocos_de_quatorze_dias():
    blocos = dividir_periodo_em_blocos(date(2026, 1, 1), date(2026, 7, 14))

    assert len(blocos) == 14
    assert blocos[0] == (date(2026, 1, 1), date(2026, 1, 14))
    assert blocos[-1] == (date(2026, 7, 2), date(2026, 7, 14))
    assert dividir_periodo_em_blocos(
        date(2026, 1, 1), date(2026, 7, 14), mais_recentes_primeiro=True
    )[0] == blocos[-1]
