from app.modules.custos.domain import ingredientes


def test_normalizar_remove_acentos_stopwords_e_descritores():
    assert ingredientes.normalizar_nome_insumo("Açúcar Refinado") == "acucar"
    assert ingredientes.normalizar_nome_insumo("Farinha de Trigo") == "farinha trigo"


def test_normalizar_aplica_substituicoes():
    assert ingredientes.normalizar_nome_insumo("Queijos") == "queijo"
    assert ingredientes.normalizar_nome_insumo("Mucarela") == "mussarela"


def test_compativeis_quando_iguais_apos_normalizar():
    assert ingredientes.nomes_insumos_compativeis("Açúcar", "acucar refinado especial")


def test_compativeis_subconjunto_nao_generico():
    assert ingredientes.nomes_insumos_compativeis("mussarela", "queijo mussarela")


def test_incompativeis_por_generico_sozinho():
    # "queijo" sozinho e generico demais para casar com "queijo mussarela".
    assert not ingredientes.nomes_insumos_compativeis("queijo", "queijo mussarela")


def test_incompativeis_sem_tokens_comuns():
    assert not ingredientes.nomes_insumos_compativeis("acucar", "farinha")


def test_deduplicar_textos_ignora_caixa_e_espacos():
    entrada = ["Sal", "sal", "  SAL  ", "Acucar"]
    assert ingredientes.deduplicar_textos(entrada) == ["Sal", "Acucar"]
