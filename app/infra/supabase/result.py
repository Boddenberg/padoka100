from collections.abc import Iterable
from typing import Any

from app.core.errors import NotFoundError


def many(rows: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return list(rows or [])


def one_or_none(rows: Iterable[dict[str, Any]] | None) -> dict[str, Any] | None:
    return next(iter(rows or []), None)


def one_or_raise(
    rows: Iterable[dict[str, Any]] | None,
    *,
    resource: str,
    resource_id: str,
) -> dict[str, Any]:
    row = one_or_none(rows)
    if row is None:
        raise NotFoundError(resource, resource_id)
    return row


def inserted_one(
    result,
    *,
    resource: str = "Registro",
    resource_id: str = "novo",
) -> dict[str, Any]:
    return one_or_raise(getattr(result, "data", None), resource=resource, resource_id=resource_id)


def updated_one(result, *, resource: str, resource_id: str) -> dict[str, Any]:
    return one_or_raise(getattr(result, "data", None), resource=resource, resource_id=resource_id)
