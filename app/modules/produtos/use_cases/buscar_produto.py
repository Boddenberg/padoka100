from datetime import date
from uuid import UUID

from app.core.clock import hoje_operacional
from app.modules.produtos.adapters.supabase_repository import (
    PrecoProdutoRepository,
    ProdutoRepository,
)
from app.modules.produtos.use_cases.shared import anexar_preco_atual


def buscar_produto(
    produto_id: UUID,
    *,
    data_preco: date | None = None,
    repository: ProdutoRepository | None = None,
    preco_repository: PrecoProdutoRepository | None = None,
) -> dict:
    repo = repository or ProdutoRepository()
    preco_repo = preco_repository or PrecoProdutoRepository(repo.client)
    produto = repo.buscar_produto(produto_id)
    return anexar_preco_atual(preco_repo, produto, data_preco or hoje_operacional())
