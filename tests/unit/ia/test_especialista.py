from app.modules.ia import servico


def test_humaniza_chave_de_jornada_com_aspas():
    texto = 'Claro! Se quiser, posso te levar para "cadastrar_produtos", e so tocar.'
    resultado = servico._humanizar_jornadas_no_texto(texto)
    assert "cadastrar_produtos" not in resultado
    assert "cadastrar seus produtos" in resultado


def test_humaniza_varias_chaves_sem_aspas():
    texto = "Da para calcular_custo e depois montar a lista em lista_compras."
    resultado = servico._humanizar_jornadas_no_texto(texto)
    assert "calcular_custo" not in resultado
    assert "lista_compras" not in resultado
    assert "calcular o custo" in resultado
    assert "montar a lista de compras" in resultado


def test_nao_mexe_em_texto_sem_chave():
    texto = "Bom dia! Posso ajudar com receitas, custos e a organizacao da padaria."
    assert servico._humanizar_jornadas_no_texto(texto) == texto
