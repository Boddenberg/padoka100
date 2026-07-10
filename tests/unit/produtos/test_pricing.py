from datetime import date

from app.modules.produtos.domain.pricing import (
    buscar_preco_anterior,
    buscar_proximo_preco,
    calcular_vigencia_ate_da_nova_versao,
    calcular_vigencia_ate_da_versao_anterior,
    preco_cobre_data,
)

VERSOES = [
    {"id": "a", "vigente_desde": "2026-01-01"},
    {"id": "b", "vigente_desde": "2026-03-01"},
    {"id": "c", "vigente_desde": "2026-06-01"},
]


def test_buscar_preco_anterior_retorna_ultima_versao_estritamente_antes():
    anterior = buscar_preco_anterior(VERSOES, date(2026, 3, 1))
    assert anterior["id"] == "a"


def test_buscar_preco_anterior_sem_candidato_retorna_none():
    assert buscar_preco_anterior(VERSOES, date(2025, 12, 1)) is None


def test_buscar_proximo_preco_retorna_primeira_versao_estritamente_depois():
    proximo = buscar_proximo_preco(VERSOES, date(2026, 3, 1))
    assert proximo["id"] == "c"


def test_buscar_proximo_preco_sem_candidato_retorna_none():
    assert buscar_proximo_preco(VERSOES, date(2026, 6, 1)) is None


def test_preco_cobre_data_quando_vigente_ate_none():
    assert preco_cobre_data({"vigente_ate": None}, date(2026, 6, 1)) is True


def test_preco_cobre_data_quando_vigente_ate_maior_ou_igual():
    assert preco_cobre_data({"vigente_ate": "2026-06-01"}, date(2026, 6, 1)) is True
    assert preco_cobre_data({"vigente_ate": "2026-05-31"}, date(2026, 6, 1)) is False


def test_calcular_vigencia_ate_da_nova_versao_sem_proxima():
    assert calcular_vigencia_ate_da_nova_versao(None) is None


def test_calcular_vigencia_ate_da_nova_versao_com_proxima():
    resultado = calcular_vigencia_ate_da_nova_versao({"vigente_desde": "2026-03-01"})
    assert resultado == date(2026, 2, 28)


def test_calcular_vigencia_ate_da_versao_anterior():
    assert calcular_vigencia_ate_da_versao_anterior(date(2026, 3, 1)) == date(2026, 2, 28)
