"""Serializacao de valores Python para o formato aceito pelo Supabase."""

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


def encode_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: encode_value(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [encode_value(item) for item in value]
    return value


def to_db_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {key: encode_value(value) for key, value in data.items() if value is not None}


def first_or_none(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    return next(iter(rows), None)
