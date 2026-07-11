"""Escopo por usuario no repositorio de vendas."""

import pytest

from app.core.errors import NotFoundError
from app.modules.vendas.adapters.supabase_repository import VendaRepository
from tests.fakes_supabase import ClienteFake, consulta_da_tabela

USUARIO_A = "11111111-1111-1111-1111-111111111111"


def test_listar_vendas_do_dia_filtra_pelo_dono():
    cliente = ClienteFake({"vendas": []})
    repo = VendaRepository(cliente, usuario_id=USUARIO_A)

    repo.listar_por_dia("dia-1")

    consulta = consulta_da_tabela(cliente, "vendas")
    assert ("usuario_id", USUARIO_A) in consulta.filtros
    assert ("dia_de_venda_id", "dia-1") in consulta.filtros


def test_buscar_venda_de_outro_dono_vira_not_found():
    cliente = ClienteFake({"vendas": []})
    repo = VendaRepository(cliente, usuario_id=USUARIO_A)

    with pytest.raises(NotFoundError):
        repo.buscar("99999999-9999-9999-9999-999999999999")

    consulta = consulta_da_tabela(cliente, "vendas")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_inserir_venda_grava_o_dono():
    cliente = ClienteFake()
    repo = VendaRepository(cliente, usuario_id=USUARIO_A)

    repo.inserir({"dia_de_venda_id": "dia-1", "situacao": "ativa"})

    consulta = consulta_da_tabela(cliente, "vendas")
    assert consulta.operacao == "insert"
    assert consulta.payload["usuario_id"] == USUARIO_A


def test_cancelar_venda_respeita_o_dono():
    cliente = ClienteFake({"vendas": [{"id": "v1", "situacao": "ativa"}]})
    repo = VendaRepository(cliente, usuario_id=USUARIO_A)

    repo.cancelar("v1", {"situacao": "cancelada"})

    consulta = consulta_da_tabela(cliente, "vendas")
    assert consulta.operacao == "update"
    assert ("usuario_id", USUARIO_A) in consulta.filtros
