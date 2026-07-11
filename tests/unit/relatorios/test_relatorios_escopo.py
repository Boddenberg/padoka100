"""Escopo por usuario nas consultas de relatorios e historico."""

from datetime import date

import pytest

from app.core.errors import NotFoundError
from app.modules.historico import servico as servico_de_historico
from app.modules.relatorios import servico as servico_de_relatorios
from tests.fakes_supabase import ClienteFake, consulta_da_tabela

USUARIO_A = "11111111-1111-1111-1111-111111111111"


def test_resumo_por_data_filtra_dias_pelo_dono(monkeypatch):
    cliente = ClienteFake({"dias_de_venda": []})
    monkeypatch.setattr(servico_de_relatorios, "get_supabase_client", lambda: cliente)

    with pytest.raises(NotFoundError):
        servico_de_relatorios.buscar_resumo_do_dia_por_data(
            date(2026, 7, 1),
            usuario_id=USUARIO_A,
        )

    consulta = consulta_da_tabela(cliente, "dias_de_venda")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_resumo_leve_do_periodo_filtra_dias_pelo_dono(monkeypatch):
    cliente = ClienteFake({"dias_de_venda": []})
    monkeypatch.setattr(servico_de_relatorios, "get_supabase_client", lambda: cliente)

    servico_de_relatorios.buscar_resumo_leve_do_periodo(
        date(2026, 7, 1),
        date(2026, 7, 5),
        usuario_id=USUARIO_A,
    )

    consulta = consulta_da_tabela(cliente, "dias_de_venda")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_linha_do_tempo_filtra_pelo_dono(monkeypatch):
    cliente = ClienteFake({"eventos_linha_do_tempo": []})
    monkeypatch.setattr(servico_de_historico, "get_supabase_client", lambda: cliente)

    servico_de_historico.listar_eventos_da_linha_do_tempo(usuario_id=USUARIO_A)

    consulta = consulta_da_tabela(cliente, "eventos_linha_do_tempo")
    assert ("usuario_id", USUARIO_A) in consulta.filtros
