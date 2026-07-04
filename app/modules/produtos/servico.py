from datetime import date, timedelta
from uuid import UUID

from supabase import Client

from app.core.errors import ConflictError, NotFoundError
from app.db.supabase import get_supabase_client
from app.modules.produtos.esquemas import (
    RequisicaoAtualizarProduto,
    RequisicaoCriarProduto,
    RequisicaoCriarVersaoDePreco,
)
from app.shared.db import first_or_none, to_db_payload
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo
from app.shared.slugs import slugify


def listar_produtos(*, somente_ativos: bool = True, data_preco: date | None = None) -> list[dict]:
    client = get_supabase_client()
    consulta = client.table("produtos").select("*").order("ordem_exibicao").order("nome")
    if somente_ativos:
        consulta = consulta.eq("situacao", "ativo")
    produtos = consulta.execute().data
    data_alvo = data_preco or date.today()
    return [_anexar_preco_atual(client, produto, data_alvo) for produto in produtos]


def buscar_produto(produto_id: UUID, *, data_preco: date | None = None) -> dict:
    client = get_supabase_client()
    produto = _buscar_linha_produto(client, produto_id)
    return _anexar_preco_atual(client, produto, data_preco or date.today())


def criar_produto(requisicao: RequisicaoCriarProduto) -> dict:
    client = get_supabase_client()
    dados_produto = to_db_payload(
        {
            "nome": requisicao.nome,
            "slug": _criar_slug_unico(client, requisicao.nome),
            "descricao": requisicao.descricao,
            "descricao_visual": requisicao.descricao_visual,
            "url_imagem_principal": requisicao.url_imagem_principal,
            "cor_botao": requisicao.cor_botao,
            "ordem_exibicao": requisicao.ordem_exibicao,
            "situacao": "ativo",
        }
    )
    produto = client.table("produtos").insert(dados_produto).execute().data[0]

    dados_preco = to_db_payload(
        {
            "produto_id": produto["id"],
            "preco_venda": requisicao.preco_venda,
            "preco_custo": requisicao.preco_custo,
            "vigente_desde": requisicao.vigente_desde,
            "motivo": requisicao.motivo_preco,
        }
    )
    preco = client.table("versoes_preco_produto").insert(dados_preco).execute().data[0]

    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="produto_criado",
        titulo=f"Produto criado: {produto['nome']}",
        tipo_entidade="produto",
        entidade_id=produto["id"],
        detalhes={"preco_inicial": preco},
    )
    produto["preco_atual"] = preco
    return produto


def atualizar_produto(produto_id: UUID, requisicao: RequisicaoAtualizarProduto) -> dict:
    client = get_supabase_client()
    produto = _buscar_linha_produto(client, produto_id)
    dados_atualizacao = requisicao.model_dump(exclude_unset=True)
    if "nome" in dados_atualizacao and dados_atualizacao["nome"] != produto["nome"]:
        dados_atualizacao["slug"] = _criar_slug_unico(
            client,
            dados_atualizacao["nome"],
            ignorar_id=produto_id,
        )
    if not dados_atualizacao:
        return _anexar_preco_atual(client, produto, date.today())

    produto_atualizado = (
        client.table("produtos")
        .update(to_db_payload(dados_atualizacao))
        .eq("id", str(produto_id))
        .execute()
        .data[0]
    )
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="produto_atualizado",
        titulo=f"Produto atualizado: {produto_atualizado['nome']}",
        tipo_entidade="produto",
        entidade_id=produto_id,
        detalhes={"campos_alterados": sorted(dados_atualizacao.keys())},
    )
    return _anexar_preco_atual(client, produto_atualizado, date.today())


def listar_versoes_de_preco(produto_id: UUID) -> list[dict]:
    client = get_supabase_client()
    _buscar_linha_produto(client, produto_id)
    return (
        client.table("versoes_preco_produto")
        .select("*")
        .eq("produto_id", str(produto_id))
        .order("vigente_desde", desc=True)
        .execute()
        .data
    )


def criar_versao_de_preco(
    produto_id: UUID,
    requisicao: RequisicaoCriarVersaoDePreco,
) -> dict:
    client = get_supabase_client()
    produto = _buscar_linha_produto(client, produto_id)
    versoes_existentes = (
        client.table("versoes_preco_produto")
        .select("*")
        .eq("produto_id", str(produto_id))
        .order("vigente_desde")
        .execute()
        .data
    )
    if any(versao["vigente_desde"] == requisicao.vigente_desde.isoformat() for versao in versoes_existentes):
        raise ConflictError(
            "Ja existe um preco cadastrado para esse produto nessa data.",
            {"produto_id": str(produto_id), "vigente_desde": requisicao.vigente_desde.isoformat()},
        )

    versao_anterior = _buscar_preco_anterior(versoes_existentes, requisicao.vigente_desde)
    proxima_versao = _buscar_proximo_preco(versoes_existentes, requisicao.vigente_desde)
    nova_vigencia_ate = None
    if proxima_versao:
        nova_vigencia_ate = date.fromisoformat(proxima_versao["vigente_desde"]) - timedelta(days=1)

    if versao_anterior and _preco_cobre_data(versao_anterior, requisicao.vigente_desde):
        vigencia_anterior_ate = requisicao.vigente_desde - timedelta(days=1)
        (
            client.table("versoes_preco_produto")
            .update(to_db_payload({"vigente_ate": vigencia_anterior_ate}))
            .eq("id", versao_anterior["id"])
            .execute()
        )

    dados_preco = to_db_payload(
        {
            "produto_id": produto_id,
            "preco_venda": requisicao.preco_venda,
            "preco_custo": requisicao.preco_custo,
            "vigente_desde": requisicao.vigente_desde,
            "vigente_ate": nova_vigencia_ate,
            "motivo": requisicao.motivo,
        }
    )
    preco = client.table("versoes_preco_produto").insert(dados_preco).execute().data[0]
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="preco_produto_alterado",
        titulo=f"Preco alterado: {produto['nome']}",
        tipo_entidade="produto",
        entidade_id=produto_id,
        detalhes={
            "novo_preco": preco,
            "vigente_desde": requisicao.vigente_desde.isoformat(),
            "motivo": requisicao.motivo,
        },
    )
    return preco


def buscar_preco_vigente(produto_id: UUID | str, data_alvo: date) -> dict:
    client = get_supabase_client()
    return _buscar_preco_vigente(client, produto_id, data_alvo)


def buscar_snapshot_do_produto(produto_id: UUID | str, data_alvo: date) -> dict:
    client = get_supabase_client()
    produto = _buscar_linha_produto(client, produto_id)
    preco = _buscar_preco_vigente(client, produto_id, data_alvo)
    return {"produto": produto, "preco": preco}


def _anexar_preco_atual(client: Client, produto: dict, data_alvo: date) -> dict:
    produto["preco_atual"] = _buscar_preco_vigente(
        client,
        produto["id"],
        data_alvo,
        obrigatorio=False,
    )
    return produto


def _buscar_linha_produto(client: Client, produto_id: UUID | str) -> dict:
    produto = first_or_none(
        client.table("produtos").select("*").eq("id", str(produto_id)).limit(1).execute().data
    )
    if not produto:
        raise NotFoundError("Produto", str(produto_id))
    return produto


def _buscar_preco_vigente(
    client: Client, produto_id: UUID | str, data_alvo: date, *, obrigatorio: bool = True
) -> dict | None:
    linhas = (
        client.table("versoes_preco_produto")
        .select("*")
        .eq("produto_id", str(produto_id))
        .lte("vigente_desde", data_alvo.isoformat())
        .or_(f"vigente_ate.is.null,vigente_ate.gte.{data_alvo.isoformat()}")
        .order("vigente_desde", desc=True)
        .limit(1)
        .execute()
        .data
    )
    preco = first_or_none(linhas)
    if obrigatorio and not preco:
        raise NotFoundError("Preco vigente do produto", str(produto_id))
    return preco


def _criar_slug_unico(client: Client, nome: str, *, ignorar_id: UUID | None = None) -> str:
    slug_base = slugify(nome)
    candidato = slug_base
    sufixo = 2
    while True:
        linhas = client.table("produtos").select("id").eq("slug", candidato).limit(1).execute().data
        existente = first_or_none(linhas)
        if not existente or (ignorar_id and existente["id"] == str(ignorar_id)):
            return candidato
        candidato = f"{slug_base}-{sufixo}"
        sufixo += 1


def _buscar_preco_anterior(versoes: list[dict], data_alvo: date) -> dict | None:
    versoes_anteriores = [
        versao for versao in versoes if date.fromisoformat(versao["vigente_desde"]) < data_alvo
    ]
    return versoes_anteriores[-1] if versoes_anteriores else None


def _buscar_proximo_preco(versoes: list[dict], data_alvo: date) -> dict | None:
    proximas_versoes = [
        versao for versao in versoes if date.fromisoformat(versao["vigente_desde"]) > data_alvo
    ]
    return proximas_versoes[0] if proximas_versoes else None


def _preco_cobre_data(versao: dict, data_alvo: date) -> bool:
    vigente_ate = versao.get("vigente_ate")
    return vigente_ate is None or date.fromisoformat(vigente_ate) >= data_alvo
