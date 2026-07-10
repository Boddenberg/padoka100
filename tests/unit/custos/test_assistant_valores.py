from decimal import Decimal
from uuid import UUID

import pytest

from app.core.errors import BadRequestError
from app.modules.custos.assistant.valores import (
    decimal_obrigatorio,
    decimal_ou_none,
    decimal_str_limpa,
    deduplicar_textos,
    float_ou_none,
    lista_de_textos,
    normalizar_chave,
    texto_ou_none,
    uuid_ou_none,
)


def test_uuid_ou_none_aceita_uuid_e_texto():
    valor = UUID(int=7)
    assert uuid_ou_none(valor) == valor
    assert uuid_ou_none(str(valor)) == valor
    assert uuid_ou_none("nao-e-uuid") is None
    assert uuid_ou_none(None) is None


def test_texto_ou_none_normaliza_espacos_e_vazio():
    assert texto_ou_none("  oi  ") == "oi"
    assert texto_ou_none("   ") is None
    assert texto_ou_none(None) is None


def test_decimal_ou_none_aceita_virgula_brasileira():
    assert decimal_ou_none("1,5") == Decimal("1.5")
    assert decimal_ou_none("") is None
    assert decimal_ou_none("abc") is None


def test_decimal_obrigatorio_rejeita_zero_e_negativo():
    assert decimal_obrigatorio("2", "campo") == Decimal("2")
    with pytest.raises(BadRequestError):
        decimal_obrigatorio("0", "campo")
    with pytest.raises(BadRequestError):
        decimal_obrigatorio(None, "campo")


def test_decimal_str_limpa_remove_zeros_a_direita():
    assert decimal_str_limpa(Decimal("1.500")) == "1.5"
    assert decimal_str_limpa(Decimal("1000")) == "1000"


def test_float_ou_none_limita_entre_0_e_1():
    assert float_ou_none(0.5) == 0.5
    assert float_ou_none(2) == 1
    assert float_ou_none(-1) == 0
    assert float_ou_none("x") is None


def test_normalizar_chave_remove_acentos_e_pontuacao():
    assert normalizar_chave("Pão-de-Queijo!") == "pao de queijo"


def test_deduplicar_textos_usa_chave_normalizada():
    assert deduplicar_textos(["Ovo", "ovo", "OVO ", "sal"]) == ["Ovo", "sal"]


def test_lista_de_textos_filtra_vazios():
    assert lista_de_textos(["a", " ", "", "b"]) == ["a", "b"]
    assert lista_de_textos("nao-lista") == []
