from uuid import UUID

from app.core.clock import hoje_operacional
from app.modules.produtos.adapters.supabase_repository import (
    PrecoProdutoRepository,
    ProdutoRepository,
)
from app.modules.produtos.domain.slug import criar_slug_unico
from app.modules.produtos.esquemas import RequisicaoAtualizarProduto
from app.modules.produtos.use_cases.shared import anexar_preco_atual
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo


def atualizar_produto(
    produto_id: UUID,
    requisicao: RequisicaoAtualizarProduto,
    *,
    repository: ProdutoRepository | None = None,
    preco_repository: PrecoProdutoRepository | None = None,
) -> dict:
    repo = repository or ProdutoRepository()
    preco_repo = preco_repository or PrecoProdutoRepository(repo.client)
    produto = repo.buscar_produto(produto_id)
    dados_atualizacao = requisicao.model_dump(exclude_unset=True)
    if "nome" in dados_atualizacao and dados_atualizacao["nome"] != produto["nome"]:
        dados_atualizacao["slug"] = criar_slug_unico(
            dados_atualizacao["nome"],
            buscar_por_slug=repo.buscar_produto_por_slug,
            ignorar_id=produto_id,
        )
    if not dados_atualizacao:
        return anexar_preco_atual(preco_repo, produto, hoje_operacional())

    produto_atualizado = repo.atualizar_produto(produto_id, dados_atualizacao)
    registrar_evento_na_linha_do_tempo(
        repo.client,
        tipo_evento="produto_atualizado",
        titulo=f"Produto atualizado: {produto_atualizado['nome']}",
        tipo_entidade="produto",
        entidade_id=produto_id,
        detalhes={"campos_alterados": sorted(dados_atualizacao.keys())},
    )
    return anexar_preco_atual(preco_repo, produto_atualizado, hoje_operacional())
