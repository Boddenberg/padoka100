from uuid import UUID

from pydantic import Field

from app.modules.vendas.esquemas import VendaSaida
from app.shared.esquemas import ApiModel


class RequisicaoInterpretarComandoDeIA(ApiModel):
    texto: str = Field(min_length=1)
    dia_de_venda_id: UUID | None = None
    thread_id: UUID | None = None
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
    thread_id: UUID
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
    thread_id: UUID | None = None
    url_audio: str | None = None
    interpretacao: RespostaInterpretarComandoDeIA | None = None


class RespostaTranscreverAudioDeVenda(ApiModel):
    transcricao: str
    thread_id: UUID | None = None
    url_audio: str | None = None
    interpretacao: RespostaInterpretarComandoDeVenda | None = None


class RespostaConfirmarComandoDeIA(ApiModel):
    interacao_ia_id: UUID
    thread_id: UUID | None = None
    acao: str
    sucesso: bool = True
    mensagem_assistente: str | None = None
    resultado: dict


class RespostaConfirmarVenda(ApiModel):
    interacao_ia_id: UUID
    thread_id: UUID | None = None
    sucesso: bool = True
    mensagem_assistente: str | None = None
    venda: VendaSaida | None = None
    resultado: dict = Field(default_factory=dict)


class MidiaRecebidaPorIA(ApiModel):
    id: UUID
    thread_id: UUID | None = None
    usuario_id: UUID | None = None
    usuario_nome_cadastrado: str | None = None
    usuario_foto_url: str | None = None
    data: str
    item: str
    interacao_ia_id: UUID | None = None
    midia_id: UUID | None = None
    nome_arquivo: str | None = None
    url_publica: str | None = None
    tipo_conteudo: str | None = None
    resposta_ia: str | None = None


class RequisicaoRejeitarComandoDeIA(ApiModel):
    motivo: str | None = Field(default=None, max_length=500)


class RespostaRejeitarComandoDeIA(ApiModel):
    interacao_ia_id: UUID
    thread_id: UUID | None = None
    sucesso: bool = True
    mensagem_assistente: str
    resultado: dict


class MidiaNaThreadIA(ApiModel):
    id: UUID
    data: str
    item: str
    midia_id: UUID | None = None
    nome_arquivo: str | None = None
    url_publica: str | None = None
    tipo_conteudo: str | None = None
    resposta_ia: str | None = None


class InteracaoNaThreadIA(ApiModel):
    interacao_ia_id: UUID
    data: str
    tipo_entrada: str
    texto_usuario: str | None = None
    resposta_ia: str | None = None
    situacao: str
    acao: str | None = None
    precisa_confirmacao: bool | None = None
    resolvido_em: str | None = None
    motivo_rejeicao: str | None = None
    mensagem_erro: str | None = None
    dados_confirmacao: dict = Field(default_factory=dict)
    midias: list[MidiaNaThreadIA] = Field(default_factory=list)


class ThreadIA(ApiModel):
    thread_id: UUID
    usuario_id: UUID | None = None
    usuario_nome_cadastrado: str | None = None
    primeira_interacao_em: str
    ultima_interacao_em: str
    desfecho: str
    total_interacoes: int
    total_midias: int
    interacoes: list[InteracaoNaThreadIA] = Field(default_factory=list)
