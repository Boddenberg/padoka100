"""Escopo por usuario no servico de locais."""

import pytest

from app.core.errors import NotFoundError
from app.modules.locais import servico
from app.modules.locais.esquemas import RequisicaoCriarLocal
from tests.fakes_supabase import ClienteFake, consulta_da_tabela

USUARIO_A = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def cliente(monkeypatch):
    cliente = ClienteFake({"locais": []})
    monkeypatch.setattr(servico, "get_supabase_client", lambda: cliente)
    return cliente


def test_listar_locais_filtra_pelo_dono(cliente):
    servico.listar_locais(usuario_id=USUARIO_A)

    consulta = consulta_da_tabela(cliente, "locais")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_buscar_local_de_outro_dono_vira_not_found(cliente):
    with pytest.raises(NotFoundError):
        servico.buscar_local("99999999-9999-9999-9999-999999999999", usuario_id=USUARIO_A)

    consulta = consulta_da_tabela(cliente, "locais")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_criar_local_grava_o_dono(cliente):
    servico.criar_local(RequisicaoCriarLocal(nome="Feira"), usuario_id=USUARIO_A)

    consulta = consulta_da_tabela(cliente, "locais")
    assert consulta.operacao == "insert"
    assert consulta.payload["usuario_id"] == USUARIO_A
