from uuid import UUID

from app.modules.produtos.adapters.supabase_repository import (
    PrecoProdutoRepository,
    ProdutoRepository,
)


def listar_versoes_de_preco(
    produto_id: UUID,
    *,
    repository: ProdutoRepository | None = None,
    preco_repository: PrecoProdutoRepository | None = None,
) -> list[dict]:
    repo = repository or ProdutoRepository()
    preco_repo = preco_repository or PrecoProdutoRepository(repo.client)
    repo.buscar_produto(produto_id)
    return preco_repo.listar_versoes(produto_id, desc=True)
