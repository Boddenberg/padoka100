"""Escopo por usuario no repositorio de produtos.

Usa um cliente fake que registra filtros e payloads: o objetivo e garantir
que toda consulta filtra por usuario_id e que toda escrita grava o dono.
"""

import pytest

from app.core.errors import NotFoundError
from app.modules.produtos.adapters.supabase_repository import ProdutoRepository
from tests.fakes_supabase import ClienteFake, consulta_da_tabela

USUARIO_A = "11111111-1111-1111-1111-111111111111"


def test_listar_produtos_filtra_pelo_dono():
    cliente = ClienteFake({"produtos": []})
    repo = ProdutoRepository(cliente, usuario_id=USUARIO_A)

    repo.listar_produtos(somente_ativos=True)

    consulta = consulta_da_tabela(cliente, "produtos")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_buscar_produto_de_outro_dono_vira_not_found():
    cliente = ClienteFake({"produtos": []})
    repo = ProdutoRepository(cliente, usuario_id=USUARIO_A)

    with pytest.raises(NotFoundError):
        repo.buscar_produto("99999999-9999-9999-9999-999999999999")

    consulta = consulta_da_tabela(cliente, "produtos")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_inserir_produto_grava_o_dono():
    cliente = ClienteFake()
    repo = ProdutoRepository(cliente, usuario_id=USUARIO_A)

    repo.inserir_produto({"nome": "Pao de Queijo"})

    consulta = consulta_da_tabela(cliente, "produtos")
    assert consulta.operacao == "insert"
    assert consulta.payload["usuario_id"] == USUARIO_A


def test_atualizar_produto_respeita_o_dono():
    cliente = ClienteFake({"produtos": [{"id": "abc", "nome": "Pao"}]})
    repo = ProdutoRepository(cliente, usuario_id=USUARIO_A)

    repo.atualizar_produto("abc", {"nome": "Pao Sovado"})

    consulta = consulta_da_tabela(cliente, "produtos")
    assert consulta.operacao == "update"
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_busca_por_slug_e_por_dono():
    cliente = ClienteFake({"produtos": []})
    repo = ProdutoRepository(cliente, usuario_id=USUARIO_A)

    repo.buscar_produto_por_slug("pao-de-queijo")

    consulta = consulta_da_tabela(cliente, "produtos")
    assert ("usuario_id", USUARIO_A) in consulta.filtros
    assert ("slug", "pao-de-queijo") in consulta.filtros


def test_sem_usuario_nao_aplica_filtro_de_dono():
    cliente = ClienteFake({"produtos": []})
    repo = ProdutoRepository(cliente)

    repo.listar_produtos(somente_ativos=False)

    consulta = consulta_da_tabela(cliente, "produtos")
    assert all(campo != "usuario_id" for campo, _ in consulta.filtros)
