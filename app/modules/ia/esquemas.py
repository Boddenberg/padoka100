from uuid import UUID

from pydantic import Field

from app.modules.vendas.esquemas import VendaSaida
from app.shared.esquemas import ApiModel


class RequisicaoInterpretarComandoDeVenda(ApiModel):
    texto: str = Field(min_length=1)
    dia_de_venda_id: UUID | None = None
    permitir_fallback: bool = True


class ItemVendaInterpretado(ApiModel):
    produto_id: UUID
    nome_produto: str
    quantidade: int = Field(gt=0)
    confianca: float = Field(ge=0, le=1)


class RespostaInterpretarComandoDeVenda(ApiModel):
    interacao_ia_id: UUID
    acao: str
    precisa_confirmacao: bool = True
    mensagem_assistente: str
    itens: list[ItemVendaInterpretado] = Field(default_factory=list)
    itens_nao_identificados: list[str] = Field(default_factory=list)
    dados_confirmacao: dict
    modelo_usado: str


class RespostaTranscreverAudioDeVenda(ApiModel):
    transcricao: str
    url_audio: str | None = None
    interpretacao: RespostaInterpretarComandoDeVenda | None = None


class RespostaConfirmarVenda(ApiModel):
    interacao_ia_id: UUID
    venda: VendaSaida

