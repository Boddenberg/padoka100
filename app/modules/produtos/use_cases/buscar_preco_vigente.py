from datetime import date
from uuid import UUID

from app.modules.produtos.adapters.supabase_repository import PrecoProdutoRepository


def buscar_preco_vigente(
    produto_id: UUID | str,
    data_alvo: date,
    *,
    repository: PrecoProdutoRepository | None = None,
) -> dict:
    repo = repository or PrecoProdutoRepository()
    return repo.buscar_vigente(produto_id, data_alvo, obrigatorio=True)
