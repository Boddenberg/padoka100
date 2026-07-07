from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.shared.esquemas import ApiModel


class RequisicaoCriarItemProducao(ApiModel):
    produto_id: UUID
    quantidade_produzida: int = Field(ge=0)
    observacoes: str | None = None


class RequisicaoDecisaoSobra(ApiModel):
    produto_id: UUID
    quantidade_usada_hoje: int = Field(ge=0)
    quantidade_nao_usada_hoje: int | None = Field(default=None, ge=0)
    observacoes: str | None = None


class ItemProducaoSaida(ApiModel):
    id: UUID
    dia_de_venda_id: UUID
    produto_id: UUID
    nome_produto_no_momento: str
    url_imagem_produto_no_momento: str | None = None
    versao_preco_id: UUID | None = None
    preco_venda_unitario_no_momento: Decimal
    preco_custo_unitario_no_momento: Decimal
    quantidade_produzida: int
    observacoes: str | None = None
    criado_em: datetime
    atualizado_em: datetime


class RequisicaoCriarDiaDeVenda(ApiModel):
    data_venda: date = Field(default_factory=date.today)
    local_id: UUID | None = None
    nome_local: str | None = None
    observacoes: str | None = None
    itens_producao: list[RequisicaoCriarItemProducao] = Field(default_factory=list)


class RequisicaoAtualizarDiaDeVenda(ApiModel):
    local_id: UUID | None = None
    nome_local: str | None = None
    observacoes: str | None = None


class RequisicaoFecharDiaDeVenda(ApiModel):
    observacoes: str | None = None


class RequisicaoIniciarDiaDeVenda(ApiModel):
    data_venda: date | None = None
    local_id: UUID | None = None
    nome_local: str | None = None
    observacoes: str | None = None
    observacoes_fechamento_dia_anterior: str | None = None
    itens_producao: list[RequisicaoCriarItemProducao] = Field(default_factory=list)
    decisoes_sobra: list[RequisicaoDecisaoSobra] = Field(default_factory=list)


class DecisaoSobraSaida(ApiModel):
    id: UUID
    dia_origem_id: UUID
    dia_destino_id: UUID
    produto_id: UUID
    nome_produto_no_momento: str
    url_imagem_produto_no_momento: str | None = None
    quantidade_sobra_origem: int
    quantidade_usada_hoje: int
    quantidade_nao_usada_hoje: int
    observacoes: str | None = None
    criado_em: datetime


class DiaDeVendaSaida(ApiModel):
    id: UUID
    data_venda: date
    local_id: UUID | None = None
    nome_local_no_momento: str | None = None
    observacoes: str | None = None
    situacao: str
    aberto_em: datetime
    fechado_em: datetime | None = None
    criado_em: datetime
    atualizado_em: datetime
    itens_producao: list[ItemProducaoSaida] = Field(default_factory=list)
    sobras_usadas_hoje: list[DecisaoSobraSaida] = Field(default_factory=list)


class SobraPendenteSaida(ApiModel):
    produto_id: UUID
    nome_produto: str
    url_imagem_produto: str | None = None
    quantidade_sobra: int
    quantidade_sugerida_para_usar: int


class IniciarDiaDeVendaSaida(ApiModel):
    acao: str = Field(pattern="^(dia_atual_aberto|dia_iniciado|decidir_sobras)$")
    mensagem: str
    data_venda: date
    dia_de_venda: DiaDeVendaSaida | None = None
    dia_anterior: DiaDeVendaSaida | None = None
    sobras_pendentes: list[SobraPendenteSaida] = Field(default_factory=list)
    decisoes_sobra: list[DecisaoSobraSaida] = Field(default_factory=list)
