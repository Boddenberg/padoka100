from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from app.shared.esquemas import ApiModel

STATUS_CUSTO_PATTERN = "^(CONFIRMADO|ESTIMADO|PENDENTE|PRECISA_REVISAR)$"


class RequisicaoCriarInsumo(ApiModel):
    nome: str = Field(min_length=1, max_length=120)
    categoria: str | None = Field(default=None, max_length=80)
    quantidade_comprada: Decimal = Field(gt=0)
    unidade_compra: str = Field(min_length=1, max_length=80)
    preco_total: Decimal = Field(ge=0)
    status: str = Field(default="CONFIRMADO", pattern=STATUS_CUSTO_PATTERN)
    observacoes: str | None = None
    vigente_desde: date = Field(default_factory=date.today)
    fornecedor: str | None = Field(default=None, max_length=120)
    fonte: str | None = Field(default=None, max_length=300)


class RequisicaoAtualizarInsumo(ApiModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    categoria: str | None = Field(default=None, max_length=80)
    quantidade_comprada: Decimal | None = Field(default=None, gt=0)
    unidade_compra: str | None = Field(default=None, min_length=1, max_length=80)
    preco_total: Decimal | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, pattern=STATUS_CUSTO_PATTERN)
    observacoes: str | None = None
    vigente_desde: date | None = None
    fornecedor: str | None = Field(default=None, max_length=120)
    fonte: str | None = Field(default=None, max_length=300)


class RequisicaoRegistrarPrecoInsumo(ApiModel):
    quantidade_comprada: Decimal = Field(gt=0)
    unidade_compra: str = Field(min_length=1, max_length=80)
    preco_total: Decimal = Field(ge=0)
    vigente_desde: date = Field(default_factory=date.today)
    origem: str = Field(default="manual", pattern="^(manual|nota|assistente|importacao)$")
    fornecedor: str | None = Field(default=None, max_length=120)
    fonte: str | None = Field(default=None, max_length=300)
    observacoes: str | None = None
    status: str = Field(default="CONFIRMADO", pattern=STATUS_CUSTO_PATTERN)


class InsumoPrecoSaida(ApiModel):
    id: UUID
    insumo_id: UUID
    quantidade_comprada: Decimal
    unidade_compra: str
    preco_total: Decimal
    custo_por_unidade: Decimal
    vigente_desde: date
    origem: str
    fornecedor: str | None = None
    fonte: str | None = None
    observacoes: str | None = None
    criado_em: datetime


class InsumoSaida(ApiModel):
    id: UUID
    nome: str
    nome_normalizado: str | None = None
    categoria: str | None = None
    quantidade_comprada: Decimal
    unidade_compra: str
    preco_total: Decimal
    custo_por_unidade: Decimal
    status: str
    observacoes: str | None = None
    ultima_compra_em: date | None = None
    preco_atual: InsumoPrecoSaida | None = None
    criado_em: datetime
    atualizado_em: datetime


class RequisicaoIngredienteReceita(ApiModel):
    insumo_id: UUID | None = None
    nome: str = Field(min_length=1, max_length=120)
    quantidade_usada: Decimal = Field(gt=0)
    unidade: str = Field(min_length=1, max_length=80)
    status: str = Field(default="CONFIRMADO", pattern=STATUS_CUSTO_PATTERN)
    observacoes: str | None = None


class RequisicaoCriarReceita(ApiModel):
    nome: str | None = Field(default=None, max_length=120)
    rendimento: Decimal = Field(gt=0)
    unidade_rendimento: str = Field(default="unidade", min_length=1, max_length=30)
    status: str = Field(default="PENDENTE", pattern=STATUS_CUSTO_PATTERN)
    observacoes: str | None = None
    ingredientes: list[RequisicaoIngredienteReceita] = Field(default_factory=list)


class RequisicaoCriarCustoAdicional(ApiModel):
    receita_id: UUID | None = None
    tipo: str = Field(pattern="^(embalagem|transporte|indireto|outro)$")
    nome: str = Field(min_length=1, max_length=120)
    valor: Decimal = Field(ge=0)
    status: str = Field(default="CONFIRMADO", pattern=STATUS_CUSTO_PATTERN)
    observacoes: str | None = None


class IngredienteReceitaSaida(ApiModel):
    id: UUID
    receita_id: UUID
    insumo_id: UUID | None = None
    nome_insumo_no_momento: str
    quantidade_usada: Decimal
    unidade: str
    custo_unitario_no_momento: Decimal | None = None
    custo_total_estimado: Decimal | None = None
    status: str
    observacoes: str | None = None
    criado_em: datetime


class ReceitaSaida(ApiModel):
    id: UUID
    produto_id: UUID
    nome: str | None = None
    rendimento: Decimal
    unidade_rendimento: str
    status: str
    observacoes: str | None = None
    criado_em: datetime
    atualizado_em: datetime
    ingredientes: list[IngredienteReceitaSaida] = Field(default_factory=list)


class CustoAdicionalSaida(ApiModel):
    id: UUID
    produto_id: UUID
    receita_id: UUID | None = None
    tipo: str
    nome: str
    valor: Decimal
    status: str
    observacoes: str | None = None
    criado_em: datetime


class CalculoCustoProdutoSaida(ApiModel):
    produto_id: UUID
    produto: str
    receita_id: UUID | None = None
    custo_total_receita: Decimal
    rendimento: Decimal | None = None
    custo_por_unidade: Decimal | None = None
    custos_incluidos: dict
    status: str
    ingredientes: list[IngredienteReceitaSaida] = Field(default_factory=list)
    custos_adicionais: list[CustoAdicionalSaida] = Field(default_factory=list)
    pendencias: list[str] = Field(default_factory=list)


class ItemAtualizacaoPrecoCompra(ApiModel):
    insumo_id: UUID | None = None
    nome: str = Field(min_length=1, max_length=160)
    categoria: str | None = Field(default=None, max_length=80)
    quantidade_comprada: Decimal | None = Field(default=None, gt=0)
    unidade_compra: str | None = Field(default=None, min_length=1, max_length=80)
    preco_total: Decimal | None = Field(default=None, ge=0)
    fornecedor: str | None = Field(default=None, max_length=120)
    observacoes: str | None = None
    confianca: float | None = Field(default=None, ge=0, le=1)


class RequisicaoAtualizarPrecosPorCompra(ApiModel):
    itens: list[ItemAtualizacaoPrecoCompra] = Field(min_length=1)
    vigente_desde: date = Field(default_factory=date.today)
    origem: str = Field(default="nota", pattern="^(manual|nota|assistente|importacao)$")
    fornecedor: str | None = Field(default=None, max_length=120)
    fonte: str | None = Field(default=None, max_length=300)
    aplicar: bool = True


class ItemResultadoAtualizacaoPreco(ApiModel):
    nome_informado: str
    acao: str
    insumo: InsumoSaida | None = None
    preco: InsumoPrecoSaida | None = None
    mensagem: str | None = None
    confianca: float | None = None


class RespostaAtualizarPrecosPorCompra(ApiModel):
    total_itens: int
    criados: int
    atualizados: int
    ignorados: int
    aplicar: bool
    itens: list[ItemResultadoAtualizacaoPreco] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)


class ItemListaComprasProduto(ApiModel):
    produto_id: UUID
    quantidade: Decimal = Field(gt=0)
    receita_id: UUID | None = None


class RequisicaoGerarListaCompras(ApiModel):
    itens: list[ItemListaComprasProduto] = Field(min_length=1)
    nome: str | None = Field(default=None, max_length=160)
    data_referencia: date = Field(default_factory=date.today)
    margem_percentual: Decimal = Field(default=0, ge=0, le=100)
    salvar: bool = False


class ContribuicaoListaComprasSaida(ApiModel):
    produto_id: UUID
    produto: str
    receita_id: UUID
    quantidade_produto: Decimal
    quantidade_base: Decimal


class ItemListaComprasSaida(ApiModel):
    chave: str
    insumo_id: UUID | None = None
    nome: str
    categoria: str | None = None
    quantidade_base: Decimal
    unidade_base: str
    quantidade_sugerida: Decimal
    unidade_sugerida: str
    custo_unitario_base: Decimal | None = None
    custo_estimado: Decimal | None = None
    status: str
    observacoes: str | None = None
    contribuicoes: list[ContribuicaoListaComprasSaida] = Field(default_factory=list)


class ListaComprasSaida(ApiModel):
    id: UUID | None = None
    nome: str | None = None
    data_referencia: date
    margem_percentual: Decimal
    total_estimado: Decimal | None = None
    itens: list[ItemListaComprasSaida]
    pendencias: list[str] = Field(default_factory=list)
    criado_em: datetime | None = None

    @model_validator(mode="after")
    def ordenar_itens(self) -> "ListaComprasSaida":
        self.itens = sorted(self.itens, key=lambda item: item.nome.lower())
        return self
