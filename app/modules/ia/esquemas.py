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
