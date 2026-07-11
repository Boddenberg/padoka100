"""Regressao do 500 no login via Supabase.

Quando a migracao 012 (coluna ``supabase_auth_id``) ainda nao foi aplicada no
banco, a sincronizacao do perfil nao pode derrubar o login com 500: ela deve
refazer a escrita sem a coluna e seguir com o usuario encontrado por e-mail.
"""

from app.modules.auth import servico

# Mensagem equivalente ao erro do PostgREST quando a coluna nao existe.
PGRST_COLUNA_AUSENTE = (
    "Could not find the 'supabase_auth_id' column of 'usuarios' in the schema cache"
)


class _Resultado:
    def __init__(self, data):
        self.data = data


class _Consulta:
    def __init__(self, client):
        self._client = client
        self._op = "select"
        self._payload = None
        self._filtros = {}

    def select(self, *_args, **_kwargs):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, coluna, valor):
        self._filtros[coluna] = valor
        return self

    def is_(self, coluna, valor):
        self._filtros[coluna] = valor
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return self._client._executar(self._op, self._payload, self._filtros)


class _ClienteFake:
    """Supabase de mentira: com ``coluna_existe=False`` qualquer leitura/escrita
    que toque ``supabase_auth_id`` levanta o erro de coluna nao migrada."""

    def __init__(self, *, coluna_existe, usuario_por_email=None):
        self.coluna_existe = coluna_existe
        self.usuario_por_email = usuario_por_email
        self.escritas = []

    def table(self, _nome):
        return _Consulta(self)

    def _executar(self, op, payload, filtros):
        toca_auth_id = "supabase_auth_id" in filtros or (
            payload is not None and "supabase_auth_id" in payload
        )
        if not self.coluna_existe and toca_auth_id:
            raise RuntimeError(PGRST_COLUNA_AUSENTE)

        if op == "select":
            if "supabase_auth_id" in filtros:
                return _Resultado([])
            if "email" in filtros:
                return _Resultado([self.usuario_por_email] if self.usuario_por_email else [])
            return _Resultado(
                [{"id": self.usuario_por_email["id"]}] if self.usuario_por_email else []
            )

        if op == "update":
            self.escritas.append(payload)
            return _Resultado([{**(self.usuario_por_email or {}), **payload}])

        if op == "insert":
            self.escritas.append(payload)
            return _Resultado(
                [
                    {
                        **payload,
                        "id": "99999999-9999-9999-9999-999999999999",
                        "papel": payload.get("papel", "usuario"),
                        "situacao": "ativo",
                        "criado_em": "2026-01-01T00:00:00+00:00",
                        "atualizado_em": "2026-01-01T00:00:00+00:00",
                    }
                ]
            )

        return _Resultado([])


USUARIO_SUPABASE = {
    "id": "11111111-1111-1111-1111-111111111111",
    "email": "dono@padoka.com",
    "user_metadata": {"name": "Dono Padoka"},
}

USUARIO_EXISTENTE = {
    "id": "729b55b5-876a-49ac-8948-0c02323932e6",
    "email": "dono@padoka.com",
    "nome": "Dono Padoka",
    "papel": "dono",
    "plano": "basico",
    "situacao": "ativo",
    "criado_em": "2026-01-01T00:00:00+00:00",
    "atualizado_em": "2026-01-01T00:00:00+00:00",
}


def test_login_supabase_sem_coluna_auth_id_nao_derruba_com_500(monkeypatch):
    fake = _ClienteFake(coluna_existe=False, usuario_por_email=dict(USUARIO_EXISTENTE))
    monkeypatch.setattr(servico, "get_supabase_client", lambda: fake)

    perfil = servico.sincronizar_usuario_supabase(USUARIO_SUPABASE)

    assert perfil["id"] == USUARIO_EXISTENTE["id"]
    assert perfil["email"] == "dono@padoka.com"
    assert fake.escritas, "esperava ao menos uma tentativa de escrita"
    assert all("supabase_auth_id" not in payload for payload in fake.escritas)


def test_primeiro_login_supabase_sem_coluna_cria_perfil(monkeypatch):
    fake = _ClienteFake(coluna_existe=False, usuario_por_email=None)
    monkeypatch.setattr(servico, "get_supabase_client", lambda: fake)

    perfil = servico.sincronizar_usuario_supabase(USUARIO_SUPABASE)

    assert perfil["email"] == "dono@padoka.com"
    assert all("supabase_auth_id" not in payload for payload in fake.escritas)


def test_login_supabase_com_coluna_grava_o_vinculo(monkeypatch):
    fake = _ClienteFake(coluna_existe=True, usuario_por_email=dict(USUARIO_EXISTENTE))
    monkeypatch.setattr(servico, "get_supabase_client", lambda: fake)

    perfil = servico.sincronizar_usuario_supabase(USUARIO_SUPABASE)

    assert perfil["email"] == "dono@padoka.com"
    assert any(
        payload.get("supabase_auth_id") == USUARIO_SUPABASE["id"] for payload in fake.escritas
    )
