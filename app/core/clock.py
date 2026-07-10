from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FUSO_HORARIO_NEGOCIO = "America/Sao_Paulo"
FUSO_HORARIO_NEGOCIO_FALLBACK = timezone(timedelta(hours=-3))


def agora_utc() -> datetime:
    return datetime.now(UTC)


def fuso_horario_negocio() -> ZoneInfo | timezone:
    try:
        return ZoneInfo(FUSO_HORARIO_NEGOCIO)
    except ZoneInfoNotFoundError:
        return FUSO_HORARIO_NEGOCIO_FALLBACK


def hoje_operacional() -> date:
    return agora_utc().astimezone(fuso_horario_negocio()).date()
