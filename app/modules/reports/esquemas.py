from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AnexoReportSaida(BaseModel):
    id: UUID | None = None
    url: str
    # imagem | audio | video | arquivo
    tipo: str = "arquivo"
    tipo_conteudo: str | None = None


class ReportSaida(BaseModel):
    """Confirmacao devolvida a quem enviou o report."""

    id: UUID
    tipo: str
    mensagem: str | None = None
    contexto: str | None = None
    plataforma: str | None = None
    app_versao: str | None = None
    status: str
    criado_em: datetime
    anexos: list[AnexoReportSaida] = Field(default_factory=list)


class ReportAdminSaida(ReportSaida):
    """Visao do admin: inclui quem enviou (nome, e-mail e foto)."""

    usuario_id: UUID | None = None
    usuario_nome: str | None = None
    usuario_email: str | None = None
    usuario_foto_url: str | None = None
    atualizado_em: datetime | None = None


class AtualizarReportRequest(BaseModel):
    status: str = Field(pattern="^(novo|lido|resolvido)$")
