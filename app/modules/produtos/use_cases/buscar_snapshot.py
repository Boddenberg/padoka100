from datetime import date
from uuid import UUID

from app.modules.produtos.adapters.supabase_repository import (
    PrecoProdutoRepository,
    ProdutoRepository,
)


def buscar_snapshot_do_produto(
    produto_id: UUID | str,
    data_alvo: date,
    *,
    usuario_id: UUID | str | None = None,
    repository: ProdutoRepository | None = None,
    preco_repository: PrecoProdutoRepository | None = None,
) -> dict:
    repo = repository or ProdutoRepository(usuario_id=usuario_id)
    preco_repo = preco_repository or PrecoProdutoRepository(repo.client)
    produto = repo.buscar_produto(produto_id)
    preco = preco_repo.buscar_vigente(produto_id, data_alvo, obrigatorio=True)
    return {"produto": produto, "preco": preco}
