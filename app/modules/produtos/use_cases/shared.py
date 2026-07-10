from datetime import date

from app.modules.produtos.adapters.supabase_repository import PrecoProdutoRepository


def anexar_preco_atual(
    repository: PrecoProdutoRepository,
    produto: dict,
    data_alvo: date,
    *,
    obrigatorio: bool = False,
) -> dict:
    produto["preco_atual"] = repository.buscar_vigente(
        produto["id"],
        data_alvo,
        obrigatorio=obrigatorio,
    )
    return produto
