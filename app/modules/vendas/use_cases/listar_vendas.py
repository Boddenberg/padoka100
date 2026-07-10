from uuid import UUID

from app.modules.dias_de_venda import servico as servico_de_dias_de_venda
from app.modules.vendas.adapters.supabase_repository import ItemVendaRepository, VendaRepository
from app.modules.vendas.use_cases.shared import anexar_itens_as_vendas


def listar_vendas(
    dia_de_venda_id: UUID,
    *,
    repository: VendaRepository | None = None,
) -> list[dict]:
    venda_repo = repository or VendaRepository()
    item_repo = ItemVendaRepository(venda_repo.client)
    servico_de_dias_de_venda.buscar_linha_dia_de_venda(venda_repo.client, dia_de_venda_id)
    vendas = venda_repo.listar_por_dia(dia_de_venda_id)
    return anexar_itens_as_vendas(item_repo, vendas)
