from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.shared.esquemas import ApiModel


class RequisicaoCriarLocal(ApiModel):
    nome: str = Field(min_length=1, max_length=120)
    endereco_texto: str | None = None
    descricao: str | None = None
    url_imagem_principal: str | None = None


class RequisicaoAtualizarLocal(ApiModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    endereco_texto: str | None = None
    descricao: str | None = None
    url_imagem_principal: str | None = None
    situacao: str | None = Field(default=None, pattern="^(ativo|inativo)$")


class LocalSaida(ApiModel):
    id: UUID
    nome: str
    endereco_texto: str | None = None
    descricao: str | None = None
    url_imagem_principal: str | None = None
    situacao: str
    criado_em: datetime
    atualizado_em: datetime
