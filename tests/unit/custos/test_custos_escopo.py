"""Escopo por usuario nas consultas do modulo de custos."""

import pytest

from app.core.errors import NotFoundError
from app.modules.custos import assistente_servico
from app.modules.custos import servico as servico_de_custos
from tests.fakes_supabase import ClienteFake, consulta_da_tabela

USUARIO_A = "11111111-1111-1111-1111-111111111111"
REGISTRO = "33333333-3333-3333-3333-333333333333"


def test_listar_insumos_filtra_pelo_dono(monkeypatch):
    cliente = ClienteFake({"insumos": []})
    monkeypatch.setattr(servico_de_custos, "get_supabase_client", lambda: cliente)

    servico_de_custos.listar_insumos(usuario_id=USUARIO_A)

    consulta = consulta_da_tabela(cliente, "insumos")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_buscar_insumo_de_outro_dono_vira_not_found(monkeypatch):
    cliente = ClienteFake({"insumos": []})
    monkeypatch.setattr(servico_de_custos, "get_supabase_client", lambda: cliente)

    with pytest.raises(NotFoundError):
        servico_de_custos.buscar_insumo(REGISTRO, usuario_id=USUARIO_A)

    consulta = consulta_da_tabela(cliente, "insumos")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_buscar_receita_de_outro_dono_vira_not_found(monkeypatch):
    cliente = ClienteFake({"receitas_produto": []})
    monkeypatch.setattr(servico_de_custos, "get_supabase_client", lambda: cliente)

    with pytest.raises(NotFoundError):
        servico_de_custos.buscar_receita(REGISTRO, usuario_id=USUARIO_A)

    consulta = consulta_da_tabela(cliente, "receitas_produto")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_listas_de_compras_filtram_pelo_dono(monkeypatch):
    cliente = ClienteFake({"listas_compras": []})
    monkeypatch.setattr(servico_de_custos, "get_supabase_client", lambda: cliente)

    servico_de_custos.listar_listas_compras(usuario_id=USUARIO_A)

    consulta = consulta_da_tabela(cliente, "listas_compras")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_sessao_de_custeio_de_outro_dono_vira_not_found(monkeypatch):
    cliente = ClienteFake({"sessoes_custeio_assistido": []})
    monkeypatch.setattr(assistente_servico, "get_supabase_client", lambda: cliente)

    with pytest.raises(NotFoundError):
        assistente_servico._buscar_sessao_bruta(REGISTRO, usuario_id=USUARIO_A)

    consulta = consulta_da_tabela(cliente, "sessoes_custeio_assistido")
    assert ("usuario_id", USUARIO_A) in consulta.filtros
