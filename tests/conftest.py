"""Configuracao de testes.

O caminho raiz do projeto entra em sys.path via ``pythonpath`` no pyproject.
Fixtures compartilhadas vivem aqui.
"""

import pytest

from app.modules.custos import conversao_ia


@pytest.fixture(autouse=True)
def conversao_ia_desligada(monkeypatch):
    """Evita chamada de rede ao LLM de equivalencia de embalagem.

    Testes que querem simular a resposta do LLM fazem seu proprio monkeypatch
    de ``conversao_ia._consultar_llm`` (que sobrepoe este).
    """
    monkeypatch.setattr(conversao_ia, "_consultar_llm", lambda **kwargs: {})
    conversao_ia.limpar_cache()
    yield
    conversao_ia.limpar_cache()
