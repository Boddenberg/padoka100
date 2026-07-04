from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.shared.esquemas import ApiModel


class RequisicaoItemVendido(ApiModel):
    produto_id: UUID
    quantidade: int = Field(gt=0)


class RequisicaoRegistrarVenda(ApiModel):
    dia_de_venda_id: UUID
    itens: list[RequisicaoItemVendido] = Field(min_length=1)
    tipo_entrada: str = Field(default="manual", pattern="^(manual|audio|ia)$")
    interacao_ia_id: UUID | None = None
    texto_original: str | None = None
    url_audio: str | None = None
    observacoes: str | None = None
    ocorrido_em: datetime | None = None


class RequisicaoCancelarVenda(ApiModel):
    motivo: str | None = None


class ItemVendidoSaida(ApiModel):
    id: UUID
    venda_id: UUID
    dia_de_venda_id: UUID
    produto_id: UUID
    nome_produto_no_momento: str
    url_imagem_produto_no_momento: str | None = None
    versao_preco_id: UUID | None = None
    preco_venda_unitario_no_momento: Decimal
    preco_custo_unitario_no_momento: Decimal
    quantidade: int
    valor_total_venda: Decimal
    valor_total_custo: Decimal
    criado_em: datetime


class VendaSaida(ApiModel):
    id: UUID
    dia_de_venda_id: UUID
    tipo_entrada: str
    interacao_ia_id: UUID | None = None
    texto_original: str | None = None
    url_audio: str | None = None
    observacoes: str | None = None
    situacao: str
    ocorrido_em: datetime
    cancelado_em: datetime | None = None
    motivo_cancelamento: str | None = None
    criado_em: datetime
    atualizado_em: datetime
    itens: list[ItemVendidoSaida] = Field(default_factory=list)
