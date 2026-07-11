"""Escopo por usuario nas buscas de dia do fluxo de iniciar dia."""

from datetime import date

from app.modules.dias_de_venda.use_cases import iniciar_dia
from tests.fakes_supabase import ClienteFake, consulta_da_tabela

USUARIO_A = "11111111-1111-1111-1111-111111111111"


def test_busca_de_dia_aberto_por_data_filtra_pelo_dono():
    cliente = ClienteFake({"dias_de_venda": []})

    iniciar_dia._buscar_dia_aberto_por_data(cliente, date(2026, 7, 10), USUARIO_A)

    consulta = consulta_da_tabela(cliente, "dias_de_venda")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_busca_de_dia_anterior_aberto_filtra_pelo_dono():
    cliente = ClienteFake({"dias_de_venda": []})

    iniciar_dia._buscar_dia_aberto_anterior(cliente, date(2026, 7, 10), USUARIO_A)

    consulta = consulta_da_tabela(cliente, "dias_de_venda")
    assert ("usuario_id", USUARIO_A) in consulta.filtros


def test_busca_de_dia_fechado_com_sobra_filtra_pelo_dono():
    cliente = ClienteFake({"dias_de_venda": []})

    iniciar_dia._buscar_dia_fechado_anterior_com_sobra_pendente(
        cliente,
        date(2026, 7, 10),
        USUARIO_A,
    )

    consulta = consulta_da_tabela(cliente, "dias_de_venda")
    assert ("usuario_id", USUARIO_A) in consulta.filtros
