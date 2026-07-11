"""Validacao de propriedade da entidade que recebe midia."""

import pytest

from app.core.errors import NotFoundError
from app.modules.midia import propriedade
from tests.fakes_supabase import ClienteFake, consulta_da_tabela

USUARIO_A = "11111111-1111-1111-1111-111111111111"
USUARIO_B = "22222222-2222-2222-2222-222222222222"
ENTIDADE = "33333333-3333-3333-3333-333333333333"


def test_sem_usuario_nao_valida_nada():
    propriedade.validar_propriedade_da_entidade("produto", ENTIDADE, None)


def test_foto_de_perfil_apenas_do_proprio_usuario():
    propriedade.validar_propriedade_da_entidade("usuario", USUARIO_A, USUARIO_A)

    with pytest.raises(NotFoundError):
        propriedade.validar_propriedade_da_entidade("usuario", USUARIO_B, USUARIO_A)


def test_interacao_ia_de_outro_dono_vira_not_found(monkeypatch):
    cliente = ClienteFake({"interacoes_ia": []})
    monkeypatch.setattr(propriedade, "get_supabase_client", lambda: cliente)

    with pytest.raises(NotFoundError):
        propriedade.validar_propriedade_da_entidade("interacao_ia", ENTIDADE, USUARIO_A)

    consulta = consulta_da_tabela(cliente, "interacoes_ia")
    assert ("usuario_id", USUARIO_A) in consulta.filtros
    assert ("id", ENTIDADE) in consulta.filtros


def test_sessao_custeio_de_outro_dono_vira_not_found(monkeypatch):
    cliente = ClienteFake({"sessoes_custeio_assistido": []})
    monkeypatch.setattr(propriedade, "get_supabase_client", lambda: cliente)

    with pytest.raises(NotFoundError):
        propriedade.validar_propriedade_da_entidade("sessao_custeio", ENTIDADE, USUARIO_A)

    consulta = consulta_da_tabela(cliente, "sessoes_custeio_assistido")
    assert ("usuario_id", USUARIO_A) in consulta.filtros
