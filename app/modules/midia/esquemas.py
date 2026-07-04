from datetime import datetime
from uuid import UUID

from app.shared.esquemas import ApiModel


class MidiaSaida(ApiModel):
    id: UUID
    tipo_entidade: str
    entidade_id: UUID
    bucket: str
    caminho_arquivo: str
    url_publica: str | None = None
    tipo_conteudo: str | None = None
    descricao: str | None = None
    texto_alternativo: str | None = None
    criado_em: datetime
