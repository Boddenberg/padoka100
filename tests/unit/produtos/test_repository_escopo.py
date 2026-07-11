"""Escopo por usuario no repositorio de produtos.

Usa um cliente fake que registra filtros e payloads: o objetivo e garantir
que toda consulta filtra por usuario_id e que toda escrita grava o dono.
"""

import pytest

from app.core.errors import NotFoundError
from app.modules.produtos.adapters.supabase_repository import ProdutoRepository

USUARIO_A = "11111111-1111-1111-1111-111111111111"


class ResultadoFake:
    def __init__(self, dados):
        self.data = dados


class ConsultaFake:
    def __init__(self, tabela: str, dados: list[dict]):
        self.tabela = tabela
        self._dados = dados
        self.filtros: list[tuple[str, object]] = []
        self.payload = None
        self.operacao = "select"

    def select(self, *_args):
        return self

    def insert(self, payload):
        self.operacao = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.operacao = "update"
        self.payload = payload
        return self

    def eq(self, campo, valor):
        self.filtros.append((campo, valor))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        if self.operacao == "insert":
            return ResultadoFake([self.payload])
        return ResultadoFake(self._dados)


class ClienteFake:
    def __init__(self, dados_por_tabela: dict[str, list[dict]] | None = None):
        self._dados = dados_por_tabela or {}
        self.consultas: list[ConsultaFake] = []

    def table(self, tabela: str) -> ConsultaFake:
        consulta = ConsultaFake(tabela, self._dados.get(tabela, []))
        self.consultas.append(consulta)
        return consulta


def consulta_da_tabela(cliente: ClienteFake, tabela: str) -> ConsultaFake:
    return next(consulta for consulta in cliente.consultas if consulta.tabela == tabela)


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
