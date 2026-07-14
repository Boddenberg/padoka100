"""Persistencia e limpeza dos lotes de seed administrativo."""

from datetime import date
from uuid import UUID

from app.shared.db import to_db_payload

ORDEM_PERSISTENCIA = (
    ("dias_de_venda", "dias_de_venda"),
    ("itens_producao", "itens_producao"),
    ("vendas", "vendas"),
    ("itens_venda", "itens_venda"),
    ("decisoes_sobra", "decisoes_sobra"),
    ("eventos", "eventos_linha_do_tempo"),
)


def persistir_lote(client, lote: dict) -> None:
    """Persiste o lote e remove suas raizes se qualquer etapa falhar.

    A exclusao dos dias aciona os cascades das tabelas filhas no Postgres. Os
    eventos sao apagados explicitamente porque sua FK usa ``on delete set null``.
    """
    dia_ids = [str(dia["id"]) for dia in lote["dias_de_venda"]]
    try:
        for chave, tabela in ORDEM_PERSISTENCIA:
            _inserir_em_lotes(client, tabela, lote[chave])
    except Exception:
        _remover_lote_parcial(client, dia_ids)
        raise


def limpar_seed_anterior(
    client,
    datas: list[date],
    marcador: str,
    *,
    usuario_id: UUID | str,
) -> int:
    linhas = (
        client.table("dias_de_venda")
        .select("id")
        .gte("data_venda", min(datas).isoformat())
        .lte("data_venda", max(datas).isoformat())
        .ilike("observacoes", f"%{marcador}%")
        .eq("usuario_id", str(usuario_id))
        .execute()
        .data
    )
    ids = [str(linha["id"]) for linha in linhas]
    if not ids:
        return 0
    _remover_lote_parcial(client, ids)
    return len(ids)


def _inserir_em_lotes(client, tabela: str, linhas: list[dict], *, tamanho: int = 500) -> None:
    for inicio in range(0, len(linhas), tamanho):
        lote = linhas[inicio : inicio + tamanho]
        if lote:
            client.table(tabela).insert([to_db_payload(linha) for linha in lote]).execute()


def _remover_lote_parcial(client, dia_ids: list[str]) -> None:
    if not dia_ids:
        return
    try:
        client.table("eventos_linha_do_tempo").delete().in_("dia_de_venda_id", dia_ids).execute()
    finally:
        client.table("dias_de_venda").delete().in_("id", dia_ids).execute()
