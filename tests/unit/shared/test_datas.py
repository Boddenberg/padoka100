from datetime import date, timedelta

import pytest

from app.core.errors import BadRequestError
from app.shared.datas import validar_data_nao_futura, validar_periodo


def test_validar_data_nao_futura_aceita_passado():
    validar_data_nao_futura(date(2000, 1, 1))  # nao deve levantar


def test_validar_data_nao_futura_rejeita_futuro():
    futuro = date.today() + timedelta(days=365)
    with pytest.raises(BadRequestError):
        validar_data_nao_futura(futuro)


def test_validar_periodo_rejeita_inicio_maior_que_fim():
    with pytest.raises(BadRequestError):
        validar_periodo(date(2020, 2, 1), date(2020, 1, 1))


def test_validar_periodo_aceita_intervalo_valido_no_passado():
    validar_periodo(date(2020, 1, 1), date(2020, 2, 1))  # nao deve levantar
