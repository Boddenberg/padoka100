from collections import defaultdict
from uuid import UUID

from app.db.supabase import get_supabase_client
from app.infra.supabase.result import coluna_ausente, tabela_ausente


def listar(
    *,
    thread_id: UUID | str | None = None,
    usuario_id: UUID | str | None = None,
    situacao: str | None = None,
    limite_threads: int = 50,
    limite_interacoes: int = 200,
) -> list[dict]:
    interacoes = _listar_interacoes(
        thread_id=thread_id,
        usuario_id=usuario_id,
        situacao=situacao,
        limite=limite_interacoes,
    )
    if not interacoes:
        return []

    thread_ids = _ids_de_threads(interacoes)
    midias = _listar_midias(thread_ids=thread_ids, usuario_id=usuario_id)
    return _montar_threads(interacoes, midias)[:limite_threads]


def _listar_interacoes(
    *,
    thread_id: UUID | str | None,
    usuario_id: UUID | str | None,
    situacao: str | None,
    limite: int,
) -> list[dict]:
    consulta = (
        get_supabase_client()
        .table("interacoes_ia")
        .select("*")
        .order("criado_em", desc=True)
        .limit(limite)
    )
    if thread_id:
        consulta = consulta.eq("thread_id", str(thread_id))
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    if situacao:
        consulta = consulta.eq("situacao", situacao)
    try:
        return consulta.execute().data
    except Exception as exc:
        if coluna_ausente(exc, "thread_id") and thread_id:
            return []
        raise


def _listar_midias(
    *,
    thread_ids: list[str],
    usuario_id: UUID | str | None,
) -> list[dict]:
    if not thread_ids:
        return []
    consulta = (
        get_supabase_client()
        .table("ia_midias_recebidas")
        .select("*")
        .in_("thread_id", thread_ids)
        .order("criado_em", desc=False)
    )
    if usuario_id:
        consulta = consulta.eq("usuario_id", str(usuario_id))
    try:
        return consulta.execute().data
    except Exception as exc:
        if tabela_ausente(exc) or coluna_ausente(exc, "thread_id"):
            return []
        raise


def _montar_threads(interacoes: list[dict], midias: list[dict]) -> list[dict]:
    midias_por_interacao = defaultdict(list)
    nomes_por_thread = {}
    for midia in midias:
        if midia.get("interacao_ia_id"):
            midias_por_interacao[str(midia["interacao_ia_id"])].append(_montar_midia(midia))
        if midia.get("usuario_nome_cadastrado"):
            nomes_por_thread.setdefault(
                _thread_id_da_linha(midia),
                midia["usuario_nome_cadastrado"],
            )

    interacoes_por_thread = defaultdict(list)
    for interacao in interacoes:
        thread_id = _thread_id_da_linha(interacao)
        interacoes_por_thread[thread_id].append(
            _montar_interacao(
                interacao,
                midias_por_interacao.get(str(interacao["id"]), []),
            )
        )

    threads = []
    for thread_id, linhas in interacoes_por_thread.items():
        linhas.sort(key=lambda item: item["data"])
        ultima = linhas[-1]
        threads.append(
            {
                "thread_id": thread_id,
                "usuario_id": _primeiro_valor(interacoes_por_thread[thread_id], "usuario_id"),
                "usuario_nome_cadastrado": nomes_por_thread.get(thread_id),
                "primeira_interacao_em": linhas[0]["data"],
                "ultima_interacao_em": ultima["data"],
                "desfecho": _desfecho(ultima["situacao"]),
                "total_interacoes": len(linhas),
                "total_midias": sum(len(linha["midias"]) for linha in linhas),
                "interacoes": linhas,
            }
        )

    threads.sort(key=lambda item: item["ultima_interacao_em"], reverse=True)
    return threads


def _montar_interacao(interacao: dict, midias: list[dict]) -> dict:
    dados_confirmacao = interacao.get("dados_confirmacao") or {}
    acao_interpretada = interacao.get("acao_interpretada") or {}
    return {
        "interacao_ia_id": interacao["id"],
        "usuario_id": interacao.get("usuario_id"),
        "data": interacao.get("criado_em"),
        "tipo_entrada": interacao["tipo_entrada"],
        "texto_usuario": interacao.get("texto_original"),
        "resposta_ia": _resposta_ia(interacao),
        "situacao": interacao["situacao"],
        "acao": dados_confirmacao.get("acao") or acao_interpretada.get("acao"),
        "precisa_confirmacao": dados_confirmacao.get("precisa_confirmacao"),
        "resolvido_em": interacao.get("resolvido_em"),
        "motivo_rejeicao": interacao.get("motivo_rejeicao"),
        "mensagem_erro": interacao.get("mensagem_erro"),
        "dados_confirmacao": dados_confirmacao,
        "midias": midias,
    }


def _montar_midia(midia: dict) -> dict:
    return {
        "id": midia["id"],
        "data": midia.get("criado_em"),
        "item": midia["item"],
        "midia_id": midia.get("midia_id"),
        "nome_arquivo": midia.get("nome_arquivo"),
        "url_publica": midia.get("url_publica"),
        "tipo_conteudo": midia.get("tipo_conteudo"),
        "resposta_ia": midia.get("resposta_ia"),
    }


def _thread_id_da_linha(linha: dict) -> str:
    return str(linha.get("thread_id") or linha["id"])


def _ids_de_threads(interacoes: list[dict]) -> list[str]:
    ids = []
    for interacao in interacoes:
        thread_id = _thread_id_da_linha(interacao)
        if thread_id not in ids:
            ids.append(thread_id)
    return ids


def _resposta_ia(interacao: dict) -> str | None:
    dados_confirmacao = interacao.get("dados_confirmacao") or {}
    acao_interpretada = interacao.get("acao_interpretada") or {}
    return dados_confirmacao.get("mensagem_confirmacao") or acao_interpretada.get(
        "mensagem_assistente"
    )


def _desfecho(situacao: str) -> str:
    if situacao == "interpretada":
        return "pendente"
    return situacao


def _primeiro_valor(linhas: list[dict], chave: str):
    for linha in linhas:
        if linha.get(chave):
            return linha[chave]
    return None
