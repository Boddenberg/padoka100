from datetime import date
from uuid import UUID

from app.core.clock import hoje_operacional
from app.core.errors import ConflictError, NotFoundError
from app.db.supabase import get_supabase_client
from app.infra.supabase.result import inserted_one, updated_one
from app.modules.produtos.domain.pricing import (
    buscar_preco_anterior,
    buscar_proximo_preco,
    calcular_vigencia_ate_da_nova_versao,
    calcular_vigencia_ate_da_versao_anterior,
    preco_cobre_data,
)
from app.modules.produtos.esquemas import (
    RequisicaoAtualizarProduto,
    RequisicaoCriarProduto,
    RequisicaoCriarVersaoDePreco,
)
from app.shared.db import first_or_none, to_db_payload
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo
from app.shared.slugs import slugify
from supabase import Client


def listar_produtos(*, somente_ativos: bool = True, data_preco: date | None = None) -> list[dict]:
    client = get_supabase_client()
    consulta = client.table("produtos").select("*").order("ordem_exibicao").order("nome")
    if somente_ativos:
        consulta = consulta.eq("situacao", "ativo")
    produtos = consulta.execute().data
    data_alvo = data_preco or hoje_operacional()
    return [_anexar_preco_atual(client, produto, data_alvo) for produto in produtos]


def formatar_produtos_para_lista_http(
    produtos: list[dict],
    *,
    somente_ativos: bool,
) -> list[dict]:
    if somente_ativos:
        return [_formatar_produto_ativo_para_lista(produto) for produto in produtos]
    return [_formatar_produto_catalogo_para_lista(produto) for produto in produtos]


def buscar_produto(produto_id: UUID, *, data_preco: date | None = None) -> dict:
    client = get_supabase_client()
    produto = _buscar_linha_produto(client, produto_id)
    return _anexar_preco_atual(client, produto, data_preco or hoje_operacional())


def criar_produto(requisicao: RequisicaoCriarProduto) -> dict:
    client = get_supabase_client()
    origem_preco, gerado_por_ia = _normalizar_origem_preco(
        requisicao.origem_preco,
        requisicao.gerado_por_ia,
    )
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
    produto = inserted_one(client.table("produtos").insert(dados_produto).execute())

    dados_preco = to_db_payload(
        {
            "produto_id": produto["id"],
            "preco_venda": requisicao.preco_venda,
            "preco_custo": requisicao.preco_custo,
            "vigente_desde": requisicao.vigente_desde,
            "motivo": requisicao.motivo_preco,
            "origem": origem_preco,
            "gerado_por_ia": gerado_por_ia,
        }
    )
    preco = inserted_one(client.table("versoes_preco_produto").insert(dados_preco).execute())

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
        return _anexar_preco_atual(client, produto, hoje_operacional())

    produto_atualizado = updated_one(
        client.table("produtos")
        .update(to_db_payload(dados_atualizacao))
        .eq("id", str(produto_id))
        .execute(),
        resource="Produto",
        resource_id=str(produto_id),
    )
    registrar_evento_na_linha_do_tempo(
        client,
        tipo_evento="produto_atualizado",
        titulo=f"Produto atualizado: {produto_atualizado['nome']}",
        tipo_entidade="produto",
        entidade_id=produto_id,
        detalhes={"campos_alterados": sorted(dados_atualizacao.keys())},
    )
    return _anexar_preco_atual(client, produto_atualizado, hoje_operacional())


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
    if any(
        versao["vigente_desde"] == requisicao.vigente_desde.isoformat()
        for versao in versoes_existentes
    ):
        raise ConflictError(
            "Ja existe um preco cadastrado para esse produto nessa data.",
            {"produto_id": str(produto_id), "vigente_desde": requisicao.vigente_desde.isoformat()},
        )

    origem_preco, gerado_por_ia = _normalizar_origem_preco(
        requisicao.origem,
        requisicao.gerado_por_ia,
    )
    versao_anterior = buscar_preco_anterior(versoes_existentes, requisicao.vigente_desde)
    proxima_versao = buscar_proximo_preco(versoes_existentes, requisicao.vigente_desde)
    nova_vigencia_ate = calcular_vigencia_ate_da_nova_versao(proxima_versao)

    if versao_anterior and preco_cobre_data(versao_anterior, requisicao.vigente_desde):
        vigencia_anterior_ate = calcular_vigencia_ate_da_versao_anterior(
            requisicao.vigente_desde
        )
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
            "origem": origem_preco,
            "gerado_por_ia": gerado_por_ia,
        }
    )
    preco = inserted_one(client.table("versoes_preco_produto").insert(dados_preco).execute())
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
            "origem": origem_preco,
            "gerado_por_ia": gerado_por_ia,
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


def _formatar_produto_ativo_para_lista(produto: dict) -> dict:
    return {
        "id": produto["id"],
        "nome": produto["nome"],
        "url_imagem_principal": produto.get("url_imagem_principal"),
        "preco_atual": _formatar_preco_para_lista(produto.get("preco_atual"), ativo=True),
    }


def _formatar_produto_catalogo_para_lista(produto: dict) -> dict:
    return {
        "id": produto["id"],
        "nome": produto["nome"],
        "descricao": produto.get("descricao"),
        "url_imagem_principal": produto.get("url_imagem_principal"),
        "cor_botao": produto.get("cor_botao"),
        "ordem_exibicao": produto.get("ordem_exibicao"),
        "situacao": produto.get("situacao"),
        "preco_atual": _formatar_preco_para_lista(produto.get("preco_atual"), ativo=False),
    }


def _formatar_preco_para_lista(preco: dict | None, *, ativo: bool) -> dict | None:
    if not preco:
        return None
    if ativo:
        return {"preco_venda": preco.get("preco_venda")}
    return {
        "preco_venda": preco.get("preco_venda"),
        "preco_custo": preco.get("preco_custo"),
        "origem": preco.get("origem"),
    }


def _normalizar_origem_preco(
    origem: str | None,
    gerado_por_ia: bool | None = None,
) -> tuple[str, bool]:
    origem_normalizada = "ia" if gerado_por_ia else (origem or "manual")
    return origem_normalizada, origem_normalizada == "ia"


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
