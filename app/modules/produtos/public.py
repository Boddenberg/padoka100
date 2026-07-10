from datetime import date
from uuid import UUID

from app.modules.produtos import servico


def listar_produtos_ativos(*, data_preco: date | None = None) -> list[dict]:
    return servico.listar_produtos(somente_ativos=True, data_preco=data_preco)


def buscar_produto(produto_id: UUID, *, data_preco: date | None = None) -> dict:
    return servico.buscar_produto(produto_id, data_preco=data_preco)


def buscar_preco_vigente(produto_id: UUID | str, data_alvo: date) -> dict:
    return servico.buscar_preco_vigente(produto_id, data_alvo)


def buscar_snapshot_do_produto(produto_id: UUID | str, data_alvo: date) -> dict:
    return servico.buscar_snapshot_do_produto(produto_id, data_alvo)
