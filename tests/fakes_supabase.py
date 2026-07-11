"""Cliente Supabase fake para testes de escopo.

Registra filtros e payloads de cada consulta; devolve os dados configurados
por tabela. Nao implementa semantica de filtro — os testes verificam se o
filtro certo foi APLICADO, nao o resultado dele. Para semantica em memoria,
ver o fake de integracao em tests/integration/.
"""

FAKE_ID = "00000000-0000-0000-0000-00000000fake"


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

    def lt(self, campo, valor):
        self.filtros.append((f"{campo}<", valor))
        return self

    def lte(self, campo, valor):
        self.filtros.append((f"{campo}<=", valor))
        return self

    def gte(self, campo, valor):
        self.filtros.append((f"{campo}>=", valor))
        return self

    def in_(self, campo, valores):
        self.filtros.append((f"{campo} in", tuple(valores)))
        return self

    def is_(self, campo, valor):
        self.filtros.append((f"{campo} is", valor))
        return self

    def or_(self, expressao):
        self.filtros.append(("or", expressao))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        if self.operacao == "insert":
            if isinstance(self.payload, list):
                return ResultadoFake([{"id": FAKE_ID, **linha} for linha in self.payload])
            return ResultadoFake([{"id": FAKE_ID, **self.payload}])
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


def consultas_da_tabela(cliente: ClienteFake, tabela: str) -> list[ConsultaFake]:
    return [consulta for consulta in cliente.consultas if consulta.tabela == tabela]
