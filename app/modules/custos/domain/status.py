STATUS_ORDEM = {
    "CONFIRMADO": 0,
    "ESTIMADO": 1,
    "PENDENTE": 2,
    "PRECISA_REVISAR": 3,
}


def consolidar_status(statuses: list[str]) -> str:
    if not statuses:
        return "PENDENTE"
    return max(statuses, key=lambda status: STATUS_ORDEM.get(status, 0))
