from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.errors import BadRequestError

FUSO_HORARIO_NEGOCIO = "America/Sao_Paulo"
FUSO_HORARIO_NEGOCIO_FALLBACK = timezone(timedelta(hours=-3))


def data_operacional_hoje() -> date:
    return datetime.now(fuso_horario_negocio()).date()


def fuso_horario_negocio():
    try:
        return ZoneInfo(FUSO_HORARIO_NEGOCIO)
    except ZoneInfoNotFoundError:
        return FUSO_HORARIO_NEGOCIO_FALLBACK


def validar_data_nao_futura(data_alvo: date, *, campo: str = "data") -> None:
    hoje = data_operacional_hoje()
    if data_alvo > hoje:
        raise BadRequestError(
            "Nao e permitido usar data futura.",
            {campo: data_alvo.isoformat(), "data_atual": hoje.isoformat()},
        )


def validar_periodo(data_inicio: date, data_fim: date) -> None:
    if data_inicio > data_fim:
        raise BadRequestError(
            "A data inicial nao pode ser maior que a data final.",
            {
                "data_inicio": data_inicio.isoformat(),
                "data_fim": data_fim.isoformat(),
            },
        )
    validar_data_nao_futura(data_inicio, campo="data_inicio")
    validar_data_nao_futura(data_fim, campo="data_fim")
