"""Leituras graduais do PostgREST sem depender do limite padrao de 1.000 linhas."""

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from app.infra.supabase.result import tabela_ausente

TAMANHO_PAGINA = 500
TAMANHO_LOTE_IDS = 100


def executar_paginado(
    criar_consulta: Callable[[], Any],
    *,
    tamanho_pagina: int = TAMANHO_PAGINA,
) -> list[dict]:
    """Executa uma consulta em paginas pequenas e devolve todas as linhas.

    ``criar_consulta`` precisa criar um builder novo a cada pagina. Isso evita
    reaproveitar estado interno do cliente Supabase e permite continuar alem do
    limite de linhas configurado no PostgREST.
    """

    linhas: list[dict] = []
    inicio = 0
    while True:
        pagina = (
            criar_consulta()
            .range(inicio, inicio + tamanho_pagina - 1)
            .execute()
            .data
            or []
        )
        linhas.extend(pagina)
        if len(pagina) < tamanho_pagina:
            return linhas
        inicio += tamanho_pagina


def executar_paginado_opcional(
    criar_consulta: Callable[[], Any],
    *,
    tamanho_pagina: int = TAMANHO_PAGINA,
) -> list[dict]:
    """Versao paginada que tolera uma tabela opcional ainda nao migrada."""

    try:
        return executar_paginado(criar_consulta, tamanho_pagina=tamanho_pagina)
    except Exception as exc:
        if tabela_ausente(exc):
            return []
        raise


def em_lotes(valores: Iterable[Any], *, tamanho: int = TAMANHO_LOTE_IDS) -> Iterator[list[Any]]:
    """Divide filtros ``in`` para manter URLs e consultas pequenas."""

    lote: list[Any] = []
    for valor in valores:
        lote.append(valor)
        if len(lote) == tamanho:
            yield lote
            lote = []
    if lote:
        yield lote
