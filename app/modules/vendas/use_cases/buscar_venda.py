from uuid import UUID

from app.modules.vendas.adapters.supabase_repository import ItemVendaRepository, VendaRepository
from app.modules.vendas.use_cases.shared import anexar_itens_as_vendas


def buscar_venda(
    venda_id: UUID,
    *,
    usuario_id: UUID | str | None = None,
    repository: VendaRepository | None = None,
) -> dict:
    venda_repo = repository or VendaRepository(usuario_id=usuario_id)
    item_repo = ItemVendaRepository(venda_repo.client)
    venda = venda_repo.buscar(venda_id)
    return anexar_itens_as_vendas(item_repo, [venda])[0]
