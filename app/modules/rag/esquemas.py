from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.shared.esquemas import ApiModel

StatusDocumentoRag = Literal["pendente", "indexado", "arquivado"]


class RequisicaoCriarDocumentoRag(ApiModel):
    tipo: str = Field(default="analise_vendas", min_length=1, max_length=80)
    titulo: str = Field(min_length=1, max_length=180)
    conteudo: str = Field(min_length=1)
    fonte: str | None = Field(default=None, max_length=300)
    tags: list[str] = Field(default_factory=list)
    metadados: dict = Field(default_factory=dict)
    status: StatusDocumentoRag = "pendente"
    tamanho_trecho: int = Field(default=1200, ge=300, le=6000)
    sobreposicao: int = Field(default=150, ge=0, le=2000)

    @model_validator(mode="after")
    def validar_sobreposicao(self) -> "RequisicaoCriarDocumentoRag":
        if self.sobreposicao >= self.tamanho_trecho:
            raise ValueError("sobreposicao precisa ser menor que tamanho_trecho.")
        return self


class TrechoRagSaida(ApiModel):
    id: UUID
    documento_id: UUID
    indice: int
    conteudo: str
    tokens_estimados: int | None = None
    metadados: dict = Field(default_factory=dict)
    embedding_model: str | None = None
    criado_em: datetime


class DocumentoRagSaida(ApiModel):
    id: UUID
    tipo: str
    titulo: str
    conteudo: str
    fonte: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadados: dict = Field(default_factory=dict)
    status: StatusDocumentoRag
    criado_por_usuario_id: UUID | None = None
    criado_em: datetime
    atualizado_em: datetime
    trechos: list[TrechoRagSaida] = Field(default_factory=list)
