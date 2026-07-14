from datetime import UTC, datetime, timedelta
from uuid import uuid4

from tests.integration.conftest import API_KEY_DE_TESTE, promover_plano, registrar_e_logar

ADMIN_HEADERS = {"X-API-Key": API_KEY_DE_TESTE}


def test_notificacao_por_plano_aparece_apenas_para_usuarios_do_plano(client):
    basico = registrar_e_logar(client, "basico@padoka.com", "Basico")
    usuario_ia = registrar_e_logar(client, "ia@padoka.com", "Usuario IA")
    promover_plano(client, usuario_ia["usuario"]["id"], "ia")

    resposta = client.post(
        "/api/v1/admin/notificacoes",
        headers=ADMIN_HEADERS,
        json={
            "titulo": "Novidade da IA",
            "corpo": "Assistente de custos liberado para o plano IA.",
            "publico": "plano",
            "planos_alvo": ["ia"],
            "publicar_agora": True,
            "expira_em_dias": 3,
        },
    )

    assert resposta.status_code == 201, resposta.text
    criada = resposta.json()
    assert criada["publico"] == "plano"
    assert criada["planos_alvo"] == ["ia"]
    assert criada["expira_em_dias"] == 3
    assert criada["expira_em"] is not None

    lista_basico = client.get("/api/v1/notificacoes", headers=basico["headers"])
    lista_ia = client.get("/api/v1/notificacoes", headers=usuario_ia["headers"])
    contagem_ia = client.get(
        "/api/v1/notificacoes/nao-lidas/contagem",
        headers=usuario_ia["headers"],
    )

    assert lista_basico.status_code == 200, lista_basico.text
    assert lista_basico.json() == []
    assert lista_ia.status_code == 200, lista_ia.text
    assert [item["id"] for item in lista_ia.json()] == [criada["id"]]
    assert contagem_ia.json()["total"] == 1


def test_notificacao_para_usuario_especifico_e_estado_lido(client):
    alvo = registrar_e_logar(client, "alvo@padoka.com", "Alvo")
    outro = registrar_e_logar(client, "outro@padoka.com", "Outro")

    resposta = client.post(
        "/api/v1/admin/notificacoes",
        headers=ADMIN_HEADERS,
        json={
            "titulo": "Aviso individual",
            "corpo": "Mensagem so para uma conta.",
            "publico": "usuario",
            "usuario_alvo_id": alvo["usuario"]["id"],
            "publicar_agora": True,
        },
    )
    assert resposta.status_code == 201, resposta.text
    notificacao_id = resposta.json()["id"]

    lista_alvo = client.get("/api/v1/notificacoes", headers=alvo["headers"])
    lista_outro = client.get("/api/v1/notificacoes", headers=outro["headers"])
    tentativa_outro = client.post(
        f"/api/v1/notificacoes/{notificacao_id}/lida",
        headers=outro["headers"],
    )
    marcar_alvo = client.post(
        f"/api/v1/notificacoes/{notificacao_id}/lida",
        headers=alvo["headers"],
    )
    contagem_alvo = client.get(
        "/api/v1/notificacoes/nao-lidas/contagem",
        headers=alvo["headers"],
    )

    assert [item["id"] for item in lista_alvo.json()] == [notificacao_id]
    assert lista_outro.json() == []
    assert tentativa_outro.status_code == 404
    assert marcar_alvo.status_code == 200, marcar_alvo.text
    assert marcar_alvo.json()["lida"] is True
    assert contagem_alvo.json()["total"] == 0


def test_feed_unico_prioriza_nao_lidas_e_resume_estado(client, banco):
    usuario = registrar_e_logar(client, "feed@padoka.com", "Feed")
    agora = datetime.now(UTC)
    # Conta criada bem antes destes avisos: todos ficam visiveis (o corte por
    # data de criacao so esconde avisos anteriores a existencia da conta).
    _antedatar_criacao_usuario(banco, usuario["usuario"]["id"], agora - timedelta(days=30))
    lida_id = str(uuid4())
    nao_lida_alta_id = str(uuid4())
    nao_lida_normal_id = str(uuid4())
    banco.tabelas["notificacoes"] = [
        _notificacao_linha(
            lida_id,
            titulo="Lida recente",
            publicado_em=agora,
            prioridade="alta",
        ),
        _notificacao_linha(
            nao_lida_normal_id,
            titulo="Nao lida normal",
            publicado_em=agora - timedelta(minutes=1),
            prioridade="normal",
        ),
        _notificacao_linha(
            nao_lida_alta_id,
            titulo="Nao lida alta",
            publicado_em=agora - timedelta(minutes=2),
            prioridade="alta",
        ),
    ]
    banco.tabelas["notificacao_visualizacoes"] = [
        {
            "id": str(uuid4()),
            "notificacao_id": lida_id,
            "usuario_id": usuario["usuario"]["id"],
            "visualizado_em": agora.isoformat(),
        }
    ]

    resposta = client.get(
        "/api/v1/notificacoes/feed?limite=2",
        headers=usuario["headers"],
    )

    assert resposta.status_code == 200, resposta.text
    payload = resposta.json()
    assert [item["id"] for item in payload["itens"]] == [
        nao_lida_alta_id,
        nao_lida_normal_id,
    ]
    assert payload["resumo"] == {
        "total": 3,
        "nao_lidas": 2,
        "lidas": 1,
        "novas": 2,
        "retornadas": 2,
    }
    assert payload["tem_mais"] is True
    assert payload["persistida"] is True
    assert set(payload["itens"][0]) == {
        "id",
        "titulo",
        "corpo",
        "prioridade",
        "publicado_em",
        "expira_em",
        "criado_em",
        "lida",
        "lida_em",
        "nova",
        "midias",
        "metadados",
    }


def test_admin_exclui_notificacao_e_limpa_expiradas(client, banco):
    usuario = registrar_e_logar(client, "notificacoes@padoka.com", "Leitor")
    _antedatar_criacao_usuario(
        banco, usuario["usuario"]["id"], datetime.now(UTC) - timedelta(days=30)
    )
    criada = client.post(
        "/api/v1/admin/notificacoes",
        headers=ADMIN_HEADERS,
        json={
            "titulo": "Sem vencimento",
            "corpo": "Continua ativa ate ser arquivada ou excluida.",
            "publico": "todos",
            "publicar_agora": True,
        },
    )
    assert criada.status_code == 201, criada.text
    notificacao_id = criada.json()["id"]
    assert criada.json()["expira_em"] is None

    banco.tabelas.setdefault("midias", []).append(
        {
            "id": str(uuid4()),
            "tipo_entidade": "notificacao",
            "entidade_id": notificacao_id,
            "url_publica": "https://cdn.fake/notificacao.png",
            "tipo_conteudo": "image/png",
            "criado_em": datetime.now(UTC).isoformat(),
            "atualizado_em": datetime.now(UTC).isoformat(),
        }
    )

    excluir = client.delete(
        f"/api/v1/admin/notificacoes/{notificacao_id}",
        headers=ADMIN_HEADERS,
    )
    assert excluir.status_code == 204, excluir.text
    assert banco.tabelas["notificacoes"] == []
    assert banco.tabelas["midias"] == []

    agora = datetime.now(UTC)
    expirado_id = str(uuid4())
    ativo_id = str(uuid4())
    banco.tabelas["notificacoes"] = [
        _notificacao_linha(
            expirado_id,
            titulo="Expirada",
            publicado_em=agora - timedelta(days=4),
            expira_em=agora - timedelta(days=1),
        ),
        _notificacao_linha(
            ativo_id,
            titulo="Ativa",
            publicado_em=agora - timedelta(days=1),
            expira_em=agora + timedelta(days=2),
        ),
    ]

    limpar = client.delete("/api/v1/admin/notificacoes/expiradas", headers=ADMIN_HEADERS)
    lista = client.get("/api/v1/notificacoes", headers=usuario["headers"])

    assert limpar.status_code == 200, limpar.text
    assert limpar.json() == {"removidas": 1}
    assert [linha["id"] for linha in banco.tabelas["notificacoes"]] == [ativo_id]
    assert [item["id"] for item in lista.json()] == [ativo_id]


def test_conta_nova_nao_ve_notificacoes_anteriores_a_criacao(client, banco):
    usuario = registrar_e_logar(client, "recem@padoka.com", "Recem Chegado")
    agora = datetime.now(UTC)
    # Conta criada ha uma hora: avisos anteriores a isso nao devem aparecer.
    _antedatar_criacao_usuario(banco, usuario["usuario"]["id"], agora - timedelta(hours=1))

    antiga_id = str(uuid4())
    nova_id = str(uuid4())
    banco.tabelas["notificacoes"] = [
        _notificacao_linha(
            antiga_id,
            titulo="Teste antigo",
            publicado_em=agora - timedelta(days=2),  # antes da conta existir
        ),
        _notificacao_linha(
            nova_id,
            titulo="Aviso novo",
            publicado_em=agora - timedelta(minutes=1),  # depois da conta, ainda ativo
        ),
    ]

    lista = client.get("/api/v1/notificacoes", headers=usuario["headers"])
    feed = client.get("/api/v1/notificacoes/feed", headers=usuario["headers"])
    contagem = client.get(
        "/api/v1/notificacoes/nao-lidas/contagem",
        headers=usuario["headers"],
    )

    assert lista.status_code == 200, lista.text
    assert [item["id"] for item in lista.json()] == [nova_id]
    assert [item["id"] for item in feed.json()["itens"]] == [nova_id]
    assert contagem.json()["total"] == 1


def _antedatar_criacao_usuario(banco, usuario_id: str, quando: datetime) -> None:
    """Ajusta a data de criacao do usuario no banco fake (para o corte por data)."""
    for linha in banco.tabelas.get("usuarios", []):
        if str(linha["id"]) == str(usuario_id):
            linha["criado_em"] = quando.isoformat()


def _notificacao_linha(
    notificacao_id: str,
    *,
    titulo: str,
    publicado_em: datetime,
    expira_em: datetime | None = None,
    prioridade: str = "normal",
) -> dict:
    agora = datetime.now(UTC).isoformat()
    return {
        "id": notificacao_id,
        "titulo": titulo,
        "corpo": "Texto da notificacao.",
        "publico": "todos",
        "planos_alvo": [],
        "usuario_alvo_id": None,
        "prioridade": prioridade,
        "status": "publicada",
        "midias": [],
        "metadados": {},
        "criado_por_usuario_id": None,
        "publicado_em": publicado_em.isoformat(),
        "expira_em": expira_em.isoformat() if expira_em else None,
        "expira_em_dias": None,
        "criado_em": agora,
        "atualizado_em": agora,
    }
