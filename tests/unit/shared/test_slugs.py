from app.shared.slugs import slugify


def test_slugify_remove_acentos_e_normaliza():
    assert slugify("Pao de Queijo") == "pao-de-queijo"


def test_slugify_trata_pontuacao_e_espacos():
    assert slugify("  Cafe!!! com leite ") == "cafe-com-leite"


def test_slugify_texto_sem_alfanumerico_usa_fallback():
    assert slugify("___") == "item"
    assert slugify("") == "item"
