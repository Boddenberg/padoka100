"""Divisao de intervalos grandes em blocos previsiveis."""

from datetime import date, timedelta

BLOCO_ANALYTICS_DIAS = 14


def dividir_periodo_em_blocos(
    data_inicio: date,
    data_fim: date,
    *,
    tamanho_dias: int = BLOCO_ANALYTICS_DIAS,
    mais_recentes_primeiro: bool = False,
) -> list[tuple[date, date]]:
    if tamanho_dias < 1:
        raise ValueError("tamanho_dias precisa ser positivo")

    blocos: list[tuple[date, date]] = []
    cursor = data_inicio
    while cursor <= data_fim:
        fim_bloco = min(cursor + timedelta(days=tamanho_dias - 1), data_fim)
        blocos.append((cursor, fim_bloco))
        cursor = fim_bloco + timedelta(days=1)
    if mais_recentes_primeiro:
        blocos.reverse()
    return blocos
