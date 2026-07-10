from app.modules.produtos.domain.price_origin import normalizar_origem_preco
from app.modules.produtos.domain.slug import criar_slug_unico


def test_criar_slug_unico_sem_colisao_usa_slug_base():
    slug = criar_slug_unico("Pao de Queijo", buscar_por_slug=lambda _: None)
    assert slug == "pao-de-queijo"


def test_criar_slug_unico_com_colisao_incrementa_sufixo():
    existentes = {"pao-de-queijo", "pao-de-queijo-2"}

    def buscar(candidato):
        return {"id": "outro"} if candidato in existentes else None

    assert criar_slug_unico("Pao de Queijo", buscar_por_slug=buscar) == "pao-de-queijo-3"


def test_criar_slug_unico_ignora_o_proprio_id():
    from uuid import UUID

    meu_id = UUID(int=1)

    def buscar(_candidato):
        return {"id": str(meu_id)}

    # o registro existente e o proprio (id casa), entao mantem o slug base.
    slug = criar_slug_unico("Pao de Queijo", buscar_por_slug=buscar, ignorar_id=meu_id)
    assert slug == "pao-de-queijo"


def test_normalizar_origem_preco_ia_tem_prioridade():
    assert normalizar_origem_preco("manual", True) == ("ia", True)


def test_normalizar_origem_preco_manual_padrao():
    assert normalizar_origem_preco(None, False) == ("manual", False)
    assert normalizar_origem_preco(None) == ("manual", False)


def test_normalizar_origem_preco_origem_explicita_ia():
    assert normalizar_origem_preco("ia") == ("ia", True)
