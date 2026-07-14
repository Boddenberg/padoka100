"""Banco Supabase fake em memoria com semantica real de filtros.

Implementa o subconjunto da API do supabase-py usado pelo backend
(select/insert/update/delete + eq/lt/lte/gte/in_/is_/or_/like/ilike +
order/limit). Permite testes de integracao multiusuario com TestClient
sem rede e sem tocar o banco real.
"""

from datetime import UTC, datetime
from uuid import uuid4


class ResultadoFake:
    def __init__(self, dados):
        self.data = dados


def _agora_iso() -> str:
    return datetime.now(UTC).isoformat()


# Colunas preenchidas automaticamente quando ausentes no insert (defaults do schema).
_DEFAULTS_POR_TABELA = {
    "dias_de_venda": {"aberto_em": _agora_iso},
    "vendas": {"ocorrido_em": _agora_iso},
    "versoes_preco_produto": {"moeda": lambda: "BRL"},
    "locais": {"situacao": lambda: "ativo"},
    "produtos": {"situacao": lambda: "ativo", "ordem_exibicao": lambda: 0},
}

_COLUNAS_PADRAO = {"criado_em": _agora_iso, "atualizado_em": _agora_iso}


def _texto(valor):
    return None if valor is None else str(valor)


def _like_para_predicado(padrao: str, *, case_sensitive: bool):
    import re

    regex = "^" + re.escape(padrao).replace("%", ".*").replace("_", ".") + "$"
    flags = 0 if case_sensitive else re.IGNORECASE

    def predicado(valor):
        return valor is not None and re.match(regex, str(valor), flags) is not None

    return predicado


class ConsultaFake:
    def __init__(self, banco: "BancoFake", tabela: str):
        self._banco = banco
        self._tabela = tabela
        self._filtros = []
        self._ordens: list[tuple[str, bool]] = []
        self._limite: int | None = None
        self._intervalo: tuple[int, int] | None = None
        self._operacao = "select"
        self._payload = None

    # -- construcao ---------------------------------------------------------
    def select(self, *_cols):
        return self

    def insert(self, payload):
        self._operacao = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._operacao = "update"
        self._payload = payload
        return self

    def delete(self):
        self._operacao = "delete"
        return self

    # -- filtros ------------------------------------------------------------
    def eq(self, campo, valor):
        self._filtros.append(lambda linha: _texto(linha.get(campo)) == _texto(valor))
        return self

    def neq(self, campo, valor):
        self._filtros.append(lambda linha: _texto(linha.get(campo)) != _texto(valor))
        return self

    def lt(self, campo, valor):
        self._filtros.append(
            lambda linha: linha.get(campo) is not None and str(linha[campo]) < str(valor)
        )
        return self

    def lte(self, campo, valor):
        self._filtros.append(
            lambda linha: linha.get(campo) is not None and str(linha[campo]) <= str(valor)
        )
        return self

    def gte(self, campo, valor):
        self._filtros.append(
            lambda linha: linha.get(campo) is not None and str(linha[campo]) >= str(valor)
        )
        return self

    def in_(self, campo, valores):
        aceitos = {_texto(valor) for valor in valores}
        self._filtros.append(lambda linha: _texto(linha.get(campo)) in aceitos)
        return self

    def is_(self, campo, valor):
        if valor == "null" or valor is None:
            self._filtros.append(lambda linha: linha.get(campo) is None)
        else:
            self._filtros.append(lambda linha: linha.get(campo) == valor)
        return self

    def like(self, campo, padrao):
        predicado = _like_para_predicado(padrao, case_sensitive=True)
        self._filtros.append(lambda linha: predicado(linha.get(campo)))
        return self

    def ilike(self, campo, padrao):
        predicado = _like_para_predicado(padrao, case_sensitive=False)
        self._filtros.append(lambda linha: predicado(linha.get(campo)))
        return self

    def or_(self, expressao: str):
        """Disjuncao no formato PostgREST: "col.is.null,col.gte.2026-01-01"."""
        clausulas = []
        for parte in expressao.split(","):
            campo, operador, valor = parte.split(".", 2)
            if operador == "is" and valor == "null":
                clausulas.append(lambda linha, campo=campo: linha.get(campo) is None)
            elif operador == "eq":
                clausulas.append(
                    lambda linha, campo=campo, valor=valor: _texto(linha.get(campo))
                    == valor
                )
            elif operador == "gte":
                clausulas.append(
                    lambda linha, campo=campo, valor=valor: linha.get(campo) is not None
                    and str(linha[campo]) >= valor
                )
            elif operador == "lte":
                clausulas.append(
                    lambda linha, campo=campo, valor=valor: linha.get(campo) is not None
                    and str(linha[campo]) <= valor
                )
            else:
                raise NotImplementedError(f"or_ nao suporta operador {operador}")
        self._filtros.append(lambda linha: any(clausula(linha) for clausula in clausulas))
        return self

    # -- apresentacao -------------------------------------------------------
    def order(self, campo, *, desc: bool = False):
        self._ordens.append((campo, desc))
        return self

    def limit(self, quantidade):
        self._limite = quantidade
        return self

    def range(self, inicio: int, fim: int):
        self._intervalo = (inicio, fim)
        return self

    # -- execucao -----------------------------------------------------------
    def execute(self) -> ResultadoFake:
        linhas = self._banco.tabelas.setdefault(self._tabela, [])
        if self._operacao == "insert":
            return ResultadoFake(self._inserir(linhas))
        selecionadas = [linha for linha in linhas if self._passa_filtros(linha)]
        if self._operacao == "update":
            for linha in selecionadas:
                linha.update(self._payload)
                if "atualizado_em" in linha:
                    linha["atualizado_em"] = _agora_iso()
            return ResultadoFake([dict(linha) for linha in selecionadas])
        if self._operacao == "delete":
            self._banco.tabelas[self._tabela] = [
                linha for linha in linhas if linha not in selecionadas
            ]
            return ResultadoFake([dict(linha) for linha in selecionadas])

        for campo, desc in reversed(self._ordens):
            selecionadas.sort(
                key=lambda linha: (linha.get(campo) is None, str(linha.get(campo))),
                reverse=desc,
            )
        if self._limite is not None:
            selecionadas = selecionadas[: self._limite]
        if self._intervalo is not None:
            inicio, fim = self._intervalo
            selecionadas = selecionadas[inicio : fim + 1]
        return ResultadoFake([dict(linha) for linha in selecionadas])

    def _passa_filtros(self, linha: dict) -> bool:
        return all(filtro(linha) for filtro in self._filtros)

    def _inserir(self, linhas: list[dict]) -> list[dict]:
        payload = self._payload if isinstance(self._payload, list) else [self._payload]
        inseridas = []
        defaults = _DEFAULTS_POR_TABELA.get(self._tabela, {})
        for item in payload:
            linha = dict(item)
            linha.setdefault("id", str(uuid4()))
            for coluna, fabrica in {**_COLUNAS_PADRAO, **defaults}.items():
                linha.setdefault(coluna, fabrica())
            linhas.append(linha)
            inseridas.append(dict(linha))
        return inseridas


class StorageBucketFake:
    def upload(self, caminho, conteudo, file_options=None):
        return {"path": caminho}

    def get_public_url(self, caminho):
        return f"https://storage.fake.local/{caminho}"


class StorageFake:
    def from_(self, _bucket):
        return StorageBucketFake()


class BancoFake:
    def __init__(self):
        self.tabelas: dict[str, list[dict]] = {}
        self.storage = StorageFake()

    def table(self, tabela: str) -> ConsultaFake:
        return ConsultaFake(self, tabela)
