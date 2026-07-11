"""Escopo por usuario no servico de locais."""

import pytest

from app.core.errors import NotFoundError
from app.modules.locais import servico
from app.modules.locais.esquemas import RequisicaoCriarLocal

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
            return ResultadoFake([{"id": "00000000-0000-0000-0000-00000000fake", **self.payload}])
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
