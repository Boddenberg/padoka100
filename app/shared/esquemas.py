from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SnapshotDePreco(ApiModel):
    versao_preco_id: UUID | None = None
    preco_venda: Decimal = Field(ge=0)
    preco_custo: Decimal = Field(ge=0)
    moeda: str = "BRL"
    vigente_desde: date
    vigente_ate: date | None = None


class EventoLinhaDoTempoSaida(ApiModel):
    id: UUID
    tipo: str
    titulo: str
    detalhes: dict
    dataHora: datetime


class CorrecaoDiaFechadoSaida(ApiModel):
    id: UUID
    dia_de_venda_id: UUID
    usuario_id: str | None = None
    motivo: str | None = None
    alteracoes: list[dict] = Field(default_factory=list)
    criado_em: datetime
