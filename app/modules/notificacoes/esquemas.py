from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.shared.esquemas import ApiModel

TipoMidiaNotificacao = Literal["imagem", "video", "gif", "arquivo", "link"]
PublicoNotificacao = Literal["todos", "admins"]
PrioridadeNotificacao = Literal["baixa", "normal", "alta"]
StatusNotificacao = Literal["rascunho", "publicada", "arquivada"]


class MidiaNotificacaoEntrada(ApiModel):
    tipo: TipoMidiaNotificacao = "link"
    url: str = Field(min_length=1, max_length=2000)
    tipo_conteudo: str | None = Field(default=None, max_length=160)
    descricao: str | None = Field(default=None, max_length=300)
    texto_alternativo: str | None = Field(default=None, max_length=300)
    thumbnail_url: str | None = Field(default=None, max_length=2000)


class MidiaNotificacaoSaida(MidiaNotificacaoEntrada):
    id: UUID | None = None
    origem: Literal["externa", "upload"] = "externa"


class MidiaNotificacaoPublicaSaida(ApiModel):
    url: str
    descricao: str | None = None


class RequisicaoCriarNotificacao(ApiModel):
    titulo: str = Field(min_length=1, max_length=160)
    corpo: str = Field(min_length=1, max_length=8000)
    publico: PublicoNotificacao = "todos"
    prioridade: PrioridadeNotificacao = "normal"
    midias: list[MidiaNotificacaoEntrada] = Field(default_factory=list)
    metadados: dict = Field(default_factory=dict)
    publicar_agora: bool = False
    expira_em: datetime | None = None


class RequisicaoAtualizarNotificacao(ApiModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=160)
    corpo: str | None = Field(default=None, min_length=1, max_length=8000)
    publico: PublicoNotificacao | None = None
    prioridade: PrioridadeNotificacao | None = None
    midias: list[MidiaNotificacaoEntrada] | None = None
    metadados: dict | None = None
    expira_em: datetime | None = None


class NotificacaoSaida(ApiModel):
    id: UUID
    titulo: str
    corpo: str
    publico: PublicoNotificacao
    prioridade: PrioridadeNotificacao
    status: StatusNotificacao
    midias: list[MidiaNotificacaoSaida] = Field(default_factory=list)
    metadados: dict = Field(default_factory=dict)
    criado_por_usuario_id: UUID | None = None
    publicado_em: datetime | None = None
    expira_em: datetime | None = None
    lida: bool = False
    lida_em: datetime | None = None
    oculta: bool = False
    oculta_em: datetime | None = None
    criado_em: datetime
    atualizado_em: datetime


class NotificacaoPublicaSaida(ApiModel):
    id: UUID
    titulo: str
    corpo: str
    publicado_em: datetime | None = None
    criado_em: datetime | None = None
    lida: bool = False
    lida_em: datetime | None = None
    midias: list[MidiaNotificacaoPublicaSaida] = Field(default_factory=list)


class EstadoNotificacaoSaida(ApiModel):
    notificacao_id: UUID
    lida: bool = False
    lida_em: datetime | None = None
    oculta: bool = False
    oculta_em: datetime | None = None
    persistida: bool = True


class ContagemNotificacoesNaoLidasSaida(ApiModel):
    total: int
    persistida: bool = True
