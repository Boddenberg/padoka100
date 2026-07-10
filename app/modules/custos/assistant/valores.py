"""Coercoes puras de valores brutos (IA, formularios) do assistente de custeio."""

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID

from app.core.errors import BadRequestError
from app.modules.custos.domain import unidades


def uuid_ou_none(valor) -> UUID | None:
    if not valor:
        return None
    try:
        return valor if isinstance(valor, UUID) else UUID(str(valor))
    except (TypeError, ValueError):
        return None


def uuid_str_ou_none(valor) -> str | None:
    uuid_valor = uuid_ou_none(valor)
    return str(uuid_valor) if uuid_valor else None


def texto_ou_none(valor) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def normalizar_unidade_de_entrada(valor) -> str | None:
    texto = texto_ou_none(valor)
    return unidades.normalizar_unidade(texto) if texto else None


def lista_ou_vazia(valor) -> list:
    return valor if isinstance(valor, list) else []


def lista_de_textos(valor) -> list[str]:
    if not isinstance(valor, list):
        return []
    return [str(item).strip() for item in valor if str(item).strip()]


def deduplicar_textos(valores: list[str]) -> list[str]:
    vistos = set()
    resultado = []
    for valor in valores:
        texto = str(valor).strip()
        chave = normalizar_chave(texto)
        if texto and chave not in vistos:
            vistos.add(chave)
            resultado.append(texto)
    return resultado


def decimal_ou_none(valor) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def decimal_obrigatorio(valor, campo: str) -> Decimal:
    numero = decimal_ou_none(valor)
    if numero is None or numero <= 0:
        raise BadRequestError(f"Campo numerico obrigatorio invalido: {campo}.")
    return numero


def decimal_str_ou_none(valor) -> str | None:
    numero = decimal_ou_none(valor)
    return str(numero) if numero is not None else None


def decimal_str_limpa(valor: Decimal) -> str:
    texto = format(valor.normalize(), "f")
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def float_ou_none(valor) -> float | None:
    if valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return max(0, min(1, numero))


def arredondar_moeda(valor: Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def arredondar_percentual(valor: Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalizar_chave(valor: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", valor)
    ascii_texto = sem_acento.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_texto.lower()).strip()


def normalizar_unidade_texto(valor: str | None) -> str | None:
    if not valor:
        return None
    return normalizar_chave(valor)
