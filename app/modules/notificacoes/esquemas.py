from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.shared.esquemas import ApiModel

TipoMidiaNotificacao = Literal["imagem", "video", "gif", "arquivo", "link"]
PublicoNotificacao = Literal["todos", "admins", "plano", "usuario"]
PlanoAlvoNotificacao = Literal["basico", "analitico", "ia", "admin"]
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
    planos_alvo: list[PlanoAlvoNotificacao] = Field(default_factory=list)
    usuario_alvo_id: UUID | None = None
    prioridade: PrioridadeNotificacao = "normal"
    midias: list[MidiaNotificacaoEntrada] = Field(default_factory=list)
    metadados: dict = Field(default_factory=dict)
    publicar_agora: bool = False
    expira_em: datetime | None = None
    expira_em_dias: int | None = Field(default=None, ge=1, le=3650)

    @model_validator(mode="after")
    def validar_alvo_e_expiracao(self):
        if self.expira_em and self.expira_em_dias:
            raise ValueError("Use expira_em ou expira_em_dias, nao os dois.")
        if self.publico == "plano" and not self.planos_alvo:
            raise ValueError("Informe planos_alvo quando publico for plano.")
        if self.publico != "plano" and self.planos_alvo:
            raise ValueError("planos_alvo so pode ser usado com publico plano.")
        if self.publico == "usuario" and not self.usuario_alvo_id:
            raise ValueError("Informe usuario_alvo_id quando publico for usuario.")
        if self.publico != "usuario" and self.usuario_alvo_id:
            raise ValueError("usuario_alvo_id so pode ser usado com publico usuario.")
        return self


class RequisicaoAtualizarNotificacao(ApiModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=160)
    corpo: str | None = Field(default=None, min_length=1, max_length=8000)
    publico: PublicoNotificacao | None = None
    planos_alvo: list[PlanoAlvoNotificacao] | None = None
    usuario_alvo_id: UUID | None = None
    prioridade: PrioridadeNotificacao | None = None
    midias: list[MidiaNotificacaoEntrada] | None = None
    metadados: dict | None = None
    expira_em: datetime | None = None
    expira_em_dias: int | None = Field(default=None, ge=1, le=3650)

    @model_validator(mode="after")
    def validar_expiracao(self):
        if self.expira_em and self.expira_em_dias:
            raise ValueError("Use expira_em ou expira_em_dias, nao os dois.")
        return self


class NotificacaoSaida(ApiModel):
    id: UUID
    titulo: str
    corpo: str
    publico: PublicoNotificacao
    planos_alvo: list[PlanoAlvoNotificacao] = Field(default_factory=list)
    usuario_alvo_id: UUID | None = None
    prioridade: PrioridadeNotificacao
    status: StatusNotificacao
    midias: list[MidiaNotificacaoSaida] = Field(default_factory=list)
    metadados: dict = Field(default_factory=dict)
    criado_por_usuario_id: UUID | None = None
    publicado_em: datetime | None = None
    expira_em: datetime | None = None
    expira_em_dias: int | None = None
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
    prioridade: PrioridadeNotificacao = "normal"
    publicado_em: datetime | None = None
    expira_em: datetime | None = None
    criado_em: datetime | None = None
    lida: bool = False
    lida_em: datetime | None = None
    nova: bool = False
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


class ResumoFeedNotificacoesSaida(ApiModel):
    total: int
    nao_lidas: int
    lidas: int
    novas: int
    retornadas: int


class FeedNotificacoesSaida(ApiModel):
    itens: list[NotificacaoPublicaSaida] = Field(default_factory=list)
    resumo: ResumoFeedNotificacoesSaida
    limite: int
    tem_mais: bool = False
    persistida: bool = True


class LimpezaNotificacoesSaida(ApiModel):
    removidas: int
