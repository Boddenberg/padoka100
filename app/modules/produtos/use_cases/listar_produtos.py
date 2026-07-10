from datetime import date

from app.core.clock import hoje_operacional
from app.modules.produtos.adapters.supabase_repository import (
    PrecoProdutoRepository,
    ProdutoRepository,
)
from app.modules.produtos.use_cases.shared import anexar_preco_atual


def listar_produtos(
    *,
    somente_ativos: bool = True,
    data_preco: date | None = None,
    repository: ProdutoRepository | None = None,
    preco_repository: PrecoProdutoRepository | None = None,
) -> list[dict]:
    repo = repository or ProdutoRepository()
    preco_repo = preco_repository or PrecoProdutoRepository(repo.client)
    data_alvo = data_preco or hoje_operacional()
    produtos = repo.listar_produtos(somente_ativos=somente_ativos)
    return [anexar_preco_atual(preco_repo, produto, data_alvo) for produto in produtos]
