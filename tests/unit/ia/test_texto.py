from datetime import date
from decimal import Decimal

from app.core.clock import hoje_operacional
from app.modules.ia.domain import texto


def test_normalizar_remove_acentos_pontuacao_e_caixa():
    assert texto.normalizar("Pão, 2x!!!") == "pao 2x"


def test_normalizar_quantidade_trata_invalidos():
    assert texto.normalizar_quantidade("3") == 3
    assert texto.normalizar_quantidade(-5) == 0
    assert texto.normalizar_quantidade(None) == 0
    assert texto.normalizar_quantidade("abc") == 0


def test_normalizar_confianca_limita_entre_0_e_1():
    assert texto.normalizar_confianca(0.5) == 0.5
    assert texto.normalizar_confianca(2) == 1
    assert texto.normalizar_confianca(-1) == 0
    assert texto.normalizar_confianca("x") == 0


def test_normalizar_data_aceita_iso_e_rejeita_lixo():
    assert texto.normalizar_data("2026-03-01") == "2026-03-01"
    assert texto.normalizar_data(date(2026, 3, 1)) == "2026-03-01"
    assert texto.normalizar_data("nao e data") is None
    assert texto.normalizar_data(None) is None


def test_normalizar_uuid_str():
    valido = "11111111-1111-1111-1111-111111111111"
    assert texto.normalizar_uuid_str(valido) == valido
    assert texto.normalizar_uuid_str("nao-uuid") is None


def test_extrair_data_do_texto_formatos():
    assert texto.extrair_data_do_texto("vendi em 2026-01-15") == "2026-01-15"
    assert texto.extrair_data_do_texto("foi dia 15/01/2026") == "2026-01-15"
    assert texto.extrair_data_do_texto("hoje vendi") == hoje_operacional().isoformat()
    assert texto.extrair_data_do_texto("sem data aqui") is None


def test_buscar_quantidade_antes_digitos_e_extenso():
    assert texto.buscar_quantidade_antes(["vendi", "3", "sonho"], 2) == 3
    assert texto.buscar_quantidade_antes(["dois", "bolos"], 1) == 2
    assert texto.buscar_quantidade_antes(["sonho"], 0) == 1  # nada antes -> 1


def test_formatar_moeda_e_itens():
    assert texto.formatar_moeda(Decimal("12.5")) == "R$ 12,50"
    itens = [{"quantidade": 2, "nome_produto": "Sonho"}]
    assert texto.formatar_itens(itens) == "2x Sonho"
    assert texto.formatar_itens([]) == "nenhum item"
