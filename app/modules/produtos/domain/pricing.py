from datetime import date, timedelta


def buscar_preco_anterior(versoes: list[dict], data_alvo: date) -> dict | None:
    versoes_anteriores = [
        versao for versao in versoes if date.fromisoformat(versao["vigente_desde"]) < data_alvo
    ]
    return versoes_anteriores[-1] if versoes_anteriores else None


def buscar_proximo_preco(versoes: list[dict], data_alvo: date) -> dict | None:
    proximas_versoes = [
        versao for versao in versoes if date.fromisoformat(versao["vigente_desde"]) > data_alvo
    ]
    return proximas_versoes[0] if proximas_versoes else None


def preco_cobre_data(versao: dict, data_alvo: date) -> bool:
    vigente_ate = versao.get("vigente_ate")
    return vigente_ate is None or date.fromisoformat(vigente_ate) >= data_alvo


def calcular_vigencia_ate_da_nova_versao(proxima_versao: dict | None) -> date | None:
    if not proxima_versao:
        return None
    return date.fromisoformat(proxima_versao["vigente_desde"]) - timedelta(days=1)


def calcular_vigencia_ate_da_versao_anterior(data_nova_versao: date) -> date:
    return data_nova_versao - timedelta(days=1)
