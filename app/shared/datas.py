from datetime import date

from app.core.clock import hoje_operacional
from app.core.errors import BadRequestError


def data_operacional_hoje() -> date:
    return hoje_operacional()


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
