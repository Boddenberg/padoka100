from uuid import UUID

import pytest

from app.core.config import Settings
from app.core.errors import BadRequestError
from app.modules.midia import servico

ENTIDADE_ID = UUID("11111111-1111-1111-1111-111111111111")


def test_upload_rejeita_tipo_de_conteudo_executavel(monkeypatch):
    monkeypatch.setattr(servico, "get_settings", lambda: Settings(max_upload_bytes=100))

    with pytest.raises(BadRequestError) as exc_info:
        servico.enviar_midia_em_bytes(
            tipo_entidade="produto",
            entidade_id=ENTIDADE_ID,
            conteudo=b"<svg><script>alert(1)</script></svg>",
            nome_arquivo="xss.svg",
            tipo_conteudo="image/svg+xml; charset=utf-8",
        )

    assert exc_info.value.details == {"tipo_conteudo": "image/svg+xml"}


def test_upload_rejeita_arquivo_acima_do_limite(monkeypatch):
    monkeypatch.setattr(servico, "get_settings", lambda: Settings(max_upload_bytes=3))

    with pytest.raises(BadRequestError) as exc_info:
        servico.enviar_midia_em_bytes(
            tipo_entidade="produto",
            entidade_id=ENTIDADE_ID,
            conteudo=b"1234",
            nome_arquivo="foto.jpg",
            tipo_conteudo="image/jpeg",
        )

    assert exc_info.value.details == {"limite_bytes": 3, "tamanho_bytes": 4}
