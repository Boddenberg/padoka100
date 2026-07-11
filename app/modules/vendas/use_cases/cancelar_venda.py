from uuid import UUID

from app.core.clock import agora_utc
from app.modules.vendas.adapters.supabase_repository import ItemVendaRepository, VendaRepository
from app.modules.vendas.esquemas import RequisicaoCancelarVenda
from app.modules.vendas.use_cases.shared import anexar_itens_as_vendas
from app.shared.linha_do_tempo import registrar_evento_na_linha_do_tempo


def cancelar_venda(
    venda_id: UUID,
    requisicao: RequisicaoCancelarVenda,
    *,
    usuario_id: UUID | str | None = None,
    repository: VendaRepository | None = None,
) -> dict:
    venda_repo = repository or VendaRepository(usuario_id=usuario_id)
    item_repo = ItemVendaRepository(venda_repo.client)
    venda = venda_repo.buscar(venda_id)
    if venda["situacao"] == "cancelada":
        return anexar_itens_as_vendas(item_repo, [venda])[0]

    venda_atualizada = venda_repo.cancelar(
        venda_id,
        {
            "situacao": "cancelada",
            "cancelado_em": agora_utc(),
            "motivo_cancelamento": requisicao.motivo,
        },
    )
    registrar_evento_na_linha_do_tempo(
        venda_repo.client,
        tipo_evento="venda_cancelada",
        titulo="Venda cancelada",
        tipo_entidade="venda",
        entidade_id=venda_id,
        dia_de_venda_id=venda_atualizada["dia_de_venda_id"],
        usuario_id=usuario_id,
        detalhes={"motivo": requisicao.motivo},
    )
    return anexar_itens_as_vendas(item_repo, [venda_atualizada])[0]
