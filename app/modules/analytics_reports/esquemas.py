from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.shared.esquemas import ApiModel

StatusRelatorio = Literal["na_fila", "processando", "pronto", "falhou"]
TipoRelatorio = Literal["analytics", "ia"]


class RequisicaoGerarRelatorio(ApiModel):
    data_inicio: date
    data_fim: date

    @model_validator(mode="after")
    def validar_periodo(self):
        if self.data_fim < self.data_inicio:
            raise ValueError("data_fim deve ser igual ou posterior a data_inicio.")
        if (self.data_fim - self.data_inicio).days > 365:
            raise ValueError("O periodo do relatorio pode ter no maximo 366 dias.")
        return self


class RelatorioAnalyticsSaida(ApiModel):
    id: UUID
    status: StatusRelatorio
    tipo: TipoRelatorio
    plano_origem: str
    data_inicio: date
    data_fim: date
    progresso: int = Field(ge=0, le=100)
    etapa: str
    titulo: str | None = None
    conteudo: dict | None = None
    modelo_ia: str | None = None
    erro: str | None = None
    solicitado_em: datetime
    iniciado_em: datetime | None = None
    concluido_em: datetime | None = None
    atualizado_em: datetime
    url_exportacao: str | None = None
    reaproveitado: bool = False


class DisponibilidadeRelatorioSaida(ApiModel):
    pode_solicitar: bool
    motivo: str | None = None
    proxima_solicitacao_em: datetime | None = None
    intervalo_dias: int | None = 7
    ilimitado: bool = False
    relatorio_em_andamento_id: UUID | None = None
    plano: str
    tipo: TipoRelatorio


class ProcessamentoPendenteSaida(ApiModel):
    agendados: int = 0
    recuperados: int = 0
