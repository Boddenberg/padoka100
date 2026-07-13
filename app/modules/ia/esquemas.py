from uuid import UUID

from pydantic import Field

from app.modules.vendas.esquemas import VendaSaida
from app.shared.esquemas import ApiModel


class RequisicaoInterpretarComandoDeIA(ApiModel):
    texto: str = Field(min_length=1)
    dia_de_venda_id: UUID | None = None
    permitir_fallback: bool = True


class RequisicaoInterpretarComandoDeVenda(RequisicaoInterpretarComandoDeIA):
    pass


class RequisicaoAnalisePadrao(ApiModel):
    data_inicio: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    data_fim: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    produto_id: UUID | None = None
    contexto_usuario: str | None = None
    filtros: dict = Field(default_factory=dict)


class RequisicaoAnaliseEspecifica(RequisicaoAnalisePadrao):
    pergunta: str = Field(min_length=1)


class RespostaDadosEstruturadosIA(ApiModel):
    periodo: dict
    faturamentoTotal: float
    quantidadeTotalProduzida: int
    quantidadeTotalVendida: int
    quantidadeTotalSobrando: int
    produtos: list[dict] = Field(default_factory=list)
    dias: list[dict] = Field(default_factory=list)
    correcoesRetroativas: list[dict] = Field(default_factory=list)


class RespostaAnaliseIA(ApiModel):
    periodo: dict
    tipo: str
    modelo_usado: str
    dados_estruturados: dict
    analise: str
    resumo: str
    principais_achados: list[str] = Field(default_factory=list)
    mais_venderam: list[dict] = Field(default_factory=list)
    mais_sobraram: list[dict] = Field(default_factory=list)
    sugestoes: list[str] = Field(default_factory=list)
    pontos_atencao: list[str] = Field(default_factory=list)


class ItemInterpretado(ApiModel):
    produto_id: UUID
    nome_produto: str
    quantidade: int = Field(gt=0)
    confianca: float = Field(ge=0, le=1)


class ItemVendaInterpretado(ItemInterpretado):
    pass


class RespostaInterpretarComandoDeIA(ApiModel):
    interacao_ia_id: UUID
    acao: str
    precisa_confirmacao: bool = True
    mensagem_assistente: str
    mensagem_confirmacao: str | None = None
    itens: list[ItemInterpretado] = Field(default_factory=list)
    itens_nao_identificados: list[str] = Field(default_factory=list)
    dados_confirmacao: dict
    modelo_usado: str


class RespostaInterpretarComandoDeVenda(RespostaInterpretarComandoDeIA):
    itens: list[ItemVendaInterpretado] = Field(default_factory=list)


class RespostaTranscreverAudioDeIA(ApiModel):
    transcricao: str
    url_audio: str | None = None
    interpretacao: RespostaInterpretarComandoDeIA | None = None


class RespostaTranscreverAudioDeVenda(ApiModel):
    transcricao: str
    url_audio: str | None = None
    interpretacao: RespostaInterpretarComandoDeVenda | None = None


class RespostaConfirmarComandoDeIA(ApiModel):
    interacao_ia_id: UUID
    acao: str
    sucesso: bool = True
    mensagem_assistente: str | None = None
    resultado: dict


class RespostaConfirmarVenda(ApiModel):
    interacao_ia_id: UUID
    sucesso: bool = True
    mensagem_assistente: str | None = None
    venda: VendaSaida | None = None
    resultado: dict = Field(default_factory=dict)


class MidiaRecebidaPorIA(ApiModel):
    id: UUID
    usuario_id: UUID | None = None
    usuario_nome_cadastrado: str | None = None
    data: str
    item: str
    interacao_ia_id: UUID | None = None
    midia_id: UUID | None = None
    nome_arquivo: str | None = None
    url_publica: str | None = None
    tipo_conteudo: str | None = None
