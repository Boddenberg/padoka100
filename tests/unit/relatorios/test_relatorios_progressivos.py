from datetime import date

from app.modules.relatorios import servico
from tests.integration.fake_supabase_db import BancoFake

USUARIO_ID = "11111111-1111-1111-1111-111111111111"
DIA_ID = "22222222-2222-2222-2222-222222222222"
PRODUTO_ID = "33333333-3333-3333-3333-333333333333"


def test_resumo_compacto_soma_mais_de_mil_vendas_sem_truncar(monkeypatch):
    banco = BancoFake()
    banco.tabelas["dias_de_venda"] = [
        {
            "id": DIA_ID,
            "usuario_id": USUARIO_ID,
            "data_venda": "2026-07-01",
            "nome_local_no_momento": "Padoka",
            "situacao": "fechado",
            "aberto_em": "2026-07-01T08:00:00+00:00",
        }
    ]
    banco.tabelas["vendas"] = [
        {
            "id": f"00000000-0000-0000-0000-{indice:012d}",
            "usuario_id": USUARIO_ID,
            "dia_de_venda_id": DIA_ID,
            "situacao": "ativa",
        }
        for indice in range(1_205)
    ]
    banco.tabelas["itens_venda"] = [
        {
            "id": f"10000000-0000-0000-0000-{indice:012d}",
            "venda_id": f"00000000-0000-0000-0000-{indice:012d}",
            "dia_de_venda_id": DIA_ID,
            "produto_id": PRODUTO_ID,
            "nome_produto_no_momento": "Pao de queijo",
            "url_imagem_produto_no_momento": None,
            "quantidade": 1,
            "valor_total_venda": "2.50",
            "valor_total_custo": "1.00",
        }
        for indice in range(1_205)
    ]
    monkeypatch.setattr(servico, "get_supabase_client", lambda: banco)

    resumo = servico.buscar_resumo_leve_do_periodo(
        date(2026, 7, 1),
        date(2026, 7, 1),
        incluir_dias=True,
        usuario_id=USUARIO_ID,
    )

    assert resumo["total_vendido"] == 1_205
    assert resumo["faturamento_bruto"] == 3_012.5
    assert len(resumo["dias"]) == 1
