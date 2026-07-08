from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.shared.esquemas import ApiModel

STATUS_SESSAO_CUSTEIO_PATTERN = (
    "^(rascunho|precisa_revisao|pronto_para_confirmar|confirmado|descartado|falhou)$"
)
TIPO_ENTRADA_CUSTEIO_PATTERN = "^(texto|audio|imagem|formulario|correcao)$"
MODO_ATUALIZACAO_RASCUNHO_PATTERN = "^(mesclar|substituir)$"


class RequisicaoCriarSessaoCusteio(ApiModel):
    produto_id: UUID | None = None
    rascunho_inicial: dict = Field(default_factory=dict)
    contexto: str | None = None


class RequisicaoEntradaTextoCusteio(ApiModel):
    texto: str = Field(min_length=1)
    contexto: str | None = None
    permitir_fallback: bool = True


class RequisicaoEntradaFormularioCusteio(ApiModel):
    dados: dict = Field(default_factory=dict)
    contexto: str | None = None


class RequisicaoAtualizarRascunhoCusteio(ApiModel):
    produto_id: UUID | None = None
    rascunho: dict = Field(default_factory=dict)
    modo: str = Field(default="mesclar", pattern=MODO_ATUALIZACAO_RASCUNHO_PATTERN)
    observacao: str | None = None


class RequisicaoConfirmarSessaoCusteio(ApiModel):
    permitir_pendencias: bool = False
    atualizar_preco_custo_produto: bool = True
    vigente_desde: date = Field(default_factory=date.today)
    motivo_preco: str | None = "Custo calculado pelo assistente"


class EntradaCusteioSaida(ApiModel):
    id: UUID
    sessao_id: UUID
    tipo: str
    texto_original: str | None = None
    url_arquivo: str | None = None
    nome_arquivo: str | None = None
    tipo_conteudo: str | None = None
    dados_extraidos: dict = Field(default_factory=dict)
    confianca: float | None = None
    modelo_usado: str | None = None
    situacao: str
    mensagem_erro: str | None = None
    criado_em: datetime


class SessaoCusteioSaida(ApiModel):
    id: UUID
    produto_id: UUID | None = None
    produto: dict | None = None
    situacao: str = Field(pattern=STATUS_SESSAO_CUSTEIO_PATTERN)
    rascunho: dict = Field(default_factory=dict)
    perguntas: list[dict] = Field(default_factory=list)
    pendencias: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    confianca_geral: float | None = None
    custo_simulado: dict = Field(default_factory=dict)
    pode_confirmar: bool = False
    proxima_acao: str
    resultado_confirmacao: dict | None = None
    mensagem_erro: str | None = None
    entradas: list[EntradaCusteioSaida] = Field(default_factory=list)
    criado_em: datetime
    atualizado_em: datetime
    confirmado_em: datetime | None = None
    descartado_em: datetime | None = None
