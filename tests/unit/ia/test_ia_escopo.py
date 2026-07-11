"""Escopo por usuario nas consultas do modulo de IA."""

from datetime import date

import pytest

from app.core.errors import NotFoundError
from app.modules.ia import servico
from tests.fakes_supabase import ClienteFake, consulta_da_tabela

USUARIO_A = "11111111-1111-1111-1111-111111111111"
INTERACAO = "33333333-3333-3333-3333-333333333333"


def test_buscar_interacao_de_outro_dono_vira_not_found():
    cliente = ClienteFake({"interacoes_ia": []})

    with pytest.raises(NotFoundError):
        servico._buscar_interacao_ia(cliente, INTERACAO, usuario_id=USUARIO_A)

    consulta = consulta_da_tabela(cliente, "interacoes_ia")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_buscar_dia_aberto_filtra_pelo_dono(monkeypatch):
    cliente = ClienteFake({"dias_de_venda": []})
    monkeypatch.setattr(servico, "get_supabase_client", lambda: cliente)

    servico._buscar_dia_aberto(date(2026, 7, 10), usuario_id=USUARIO_A)

    consulta = consulta_da_tabela(cliente, "dias_de_venda")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_ultima_venda_ativa_filtra_pelo_dono(monkeypatch):
    cliente = ClienteFake({"vendas": [], "dias_de_venda": []})
    monkeypatch.setattr(servico, "get_supabase_client", lambda: cliente)

    servico._buscar_ultima_venda_ativa(
        dia_de_venda_id=None,
        data_venda=None,
        usuario_id=USUARIO_A,
    )

    consulta = consulta_da_tabela(cliente, "vendas")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_dados_estruturados_filtram_dias_pelo_dono(monkeypatch):
    cliente = ClienteFake({"dias_de_venda": []})
    monkeypatch.setattr(servico, "get_supabase_client", lambda: cliente)

    servico.montar_dados_estruturados_periodo(
        data_inicio="2026-07-01",
        data_fim="2026-07-05",
        usuario_id=USUARIO_A,
    )

    consulta = consulta_da_tabela(cliente, "dias_de_venda")
    assert ("usuario_id", USUARIO_A) in consulta.filtros
