from datetime import date, datetime

from app.core.clock import agora_utc, fuso_horario_negocio, hoje_operacional


def test_agora_utc_e_timezone_aware():
    agora = agora_utc()
    assert isinstance(agora, datetime)
    assert agora.tzinfo is not None


def test_hoje_operacional_retorna_data():
    assert isinstance(hoje_operacional(), date)


def test_fuso_horario_negocio_resolve():
    assert fuso_horario_negocio() is not None
