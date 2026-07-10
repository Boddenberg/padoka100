from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.modules.custos import assistente_servico, servico
from app.modules.custos.assistente_esquemas import (
    RequisicaoAtualizarRascunhoCusteio,
    RequisicaoConfirmarSessaoCusteio,
    RequisicaoCriarSessaoCusteio,
    RequisicaoEntradaFormularioCusteio,
    RequisicaoEntradaTextoCusteio,
    SessaoCusteioSaida,
)
from app.modules.custos.esquemas import (
    CalculoCustoProdutoSaida,
    CustoAdicionalSaida,
    InsumoPrecoSaida,
    InsumoSaida,
    ListaComprasSaida,
    ProdutoComReceitaSaida,
    ReceitaSaida,
    RequisicaoAtualizarInsumo,
    RequisicaoAtualizarPrecosPorCompra,
    RequisicaoCriarCustoAdicional,
    RequisicaoCriarInsumo,
    RequisicaoCriarReceita,
    RequisicaoGerarListaCompras,
    RequisicaoRegistrarPrecoInsumo,
    RespostaAtualizarPrecosPorCompra,
)

router = APIRouter(prefix="/custos", tags=["custos"])


@router.get("/insumos", response_model=list[InsumoSaida])
def listar_insumos() -> list[dict]:
    return servico.listar_insumos()


@router.post("/insumos", response_model=InsumoSaida, status_code=201)
def criar_insumo(requisicao: RequisicaoCriarInsumo) -> dict:
    return servico.criar_insumo(requisicao)


@router.patch("/insumos/{insumo_id}", response_model=InsumoSaida)
def atualizar_insumo(insumo_id: UUID, requisicao: RequisicaoAtualizarInsumo) -> dict:
    return servico.atualizar_insumo(insumo_id, requisicao)


@router.get("/insumos/{insumo_id}/precos", response_model=list[InsumoPrecoSaida])
def listar_precos_insumo(insumo_id: UUID) -> list[dict]:
    return servico.listar_precos_insumo(insumo_id)


@router.post("/insumos/{insumo_id}/precos", response_model=InsumoSaida, status_code=201)
def registrar_preco_insumo(
    insumo_id: UUID,
    requisicao: RequisicaoRegistrarPrecoInsumo,
) -> dict:
    return servico.registrar_preco_insumo(insumo_id, requisicao)["insumo"]


@router.post(
    "/compras/atualizar-precos",
    response_model=RespostaAtualizarPrecosPorCompra,
)
def atualizar_precos_por_compra(requisicao: RequisicaoAtualizarPrecosPorCompra) -> dict:
    return servico.atualizar_precos_por_compra(requisicao)


@router.post(
    "/compras/nota/atualizar-precos",
    response_model=RespostaAtualizarPrecosPorCompra,
)
async def atualizar_precos_por_nota_arquivo(
    file: Annotated[UploadFile, File()],
    vigente_desde: Annotated[date | None, Form()] = None,
    fornecedor: Annotated[str | None, Form()] = None,
    fonte: Annotated[str | None, Form()] = None,
    aplicar: Annotated[bool, Form()] = True,
    contexto: Annotated[str | None, Form()] = None,
) -> dict:
    return await servico.atualizar_precos_por_nota_arquivo(
        file=file,
        vigente_desde=vigente_desde or date.today(),
        fornecedor=fornecedor,
        fonte=fonte,
        aplicar=aplicar,
        contexto=contexto,
    )


@router.get("/produtos-com-receita", response_model=list[ProdutoComReceitaSaida])
def listar_produtos_com_receita() -> list[dict]:
    return servico.listar_produtos_com_receita()


@router.get("/produtos/{produto_id}/receitas", response_model=list[ReceitaSaida])
def listar_receitas_do_produto(produto_id: UUID) -> list[dict]:
    return servico.listar_receitas_do_produto(produto_id)


@router.post("/produtos/{produto_id}/receitas", response_model=ReceitaSaida, status_code=201)
def criar_receita(produto_id: UUID, requisicao: RequisicaoCriarReceita) -> dict:
    return servico.criar_receita(produto_id, requisicao)


@router.post(
    "/produtos/{produto_id}/custos-adicionais",
    response_model=CustoAdicionalSaida,
    status_code=201,
)
def criar_custo_adicional(
    produto_id: UUID,
    requisicao: RequisicaoCriarCustoAdicional,
) -> dict:
    return servico.criar_custo_adicional(produto_id, requisicao)


@router.get("/produtos/{produto_id}/calculo", response_model=CalculoCustoProdutoSaida)
def calcular_custo_do_produto(
    produto_id: UUID,
    receita_id: Annotated[UUID | None, Query()] = None,
    data_referencia: Annotated[date | None, Query()] = None,
) -> dict:
    return servico.calcular_custo_do_produto(
        produto_id,
        receita_id=receita_id,
        data_referencia=data_referencia,
    )


@router.post("/lista-compras", response_model=ListaComprasSaida)
def gerar_lista_compras(requisicao: RequisicaoGerarListaCompras) -> dict:
    return servico.gerar_lista_compras(requisicao)


@router.get("/listas-compras", response_model=list[ListaComprasSaida])
def listar_listas_compras(
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict]:
    return servico.listar_listas_compras(limite=limite)


@router.get("/listas-compras/{lista_id}", response_model=ListaComprasSaida)
def buscar_lista_compras(lista_id: UUID) -> dict:
    return servico.buscar_lista_compras(lista_id)


@router.post("/assistente/sessoes", response_model=SessaoCusteioSaida, status_code=201)
def criar_sessao_de_custeio(requisicao: RequisicaoCriarSessaoCusteio) -> dict:
    return assistente_servico.criar_sessao(requisicao)


@router.get("/assistente/sessoes/{sessao_id}", response_model=SessaoCusteioSaida)
def buscar_sessao_de_custeio(sessao_id: UUID) -> dict:
    return assistente_servico.buscar_sessao(sessao_id)


@router.post(
    "/assistente/sessoes/{sessao_id}/entradas/texto",
    response_model=SessaoCusteioSaida,
)
def adicionar_texto_ao_custeio(
    sessao_id: UUID,
    requisicao: RequisicaoEntradaTextoCusteio,
) -> dict:
    return assistente_servico.adicionar_entrada_texto(sessao_id, requisicao)


@router.post(
    "/assistente/sessoes/{sessao_id}/entradas/formulario",
    response_model=SessaoCusteioSaida,
)
def adicionar_formulario_ao_custeio(
    sessao_id: UUID,
    requisicao: RequisicaoEntradaFormularioCusteio,
) -> dict:
    return assistente_servico.adicionar_entrada_formulario(sessao_id, requisicao)


@router.post(
    "/assistente/sessoes/{sessao_id}/entradas/arquivo",
    response_model=SessaoCusteioSaida,
)
async def adicionar_arquivo_ao_custeio(
    sessao_id: UUID,
    file: Annotated[UploadFile, File()],
    tipo: Annotated[str, Form(pattern="^(audio|imagem)$")],
    contexto: Annotated[str | None, Form()] = None,
    finalidade: Annotated[str, Form(pattern="^(auto|receita|compras|completo)$")] = "auto",
    permitir_fallback: Annotated[bool, Form()] = True,
) -> dict:
    return await assistente_servico.adicionar_entrada_arquivo(
        sessao_id,
        tipo=tipo,
        file=file,
        contexto=contexto,
        finalidade=finalidade,
        permitir_fallback=permitir_fallback,
    )


@router.patch(
    "/assistente/sessoes/{sessao_id}/rascunho",
    response_model=SessaoCusteioSaida,
)
def atualizar_rascunho_de_custeio(
    sessao_id: UUID,
    requisicao: RequisicaoAtualizarRascunhoCusteio,
) -> dict:
    return assistente_servico.atualizar_rascunho(sessao_id, requisicao)


@router.post(
    "/assistente/sessoes/{sessao_id}/confirmar",
    response_model=SessaoCusteioSaida,
)
def confirmar_sessao_de_custeio(
    sessao_id: UUID,
    requisicao: RequisicaoConfirmarSessaoCusteio,
) -> dict:
    return assistente_servico.confirmar_sessao(sessao_id, requisicao)


@router.post(
    "/assistente/sessoes/{sessao_id}/descartar",
    response_model=SessaoCusteioSaida,
)
def descartar_sessao_de_custeio(sessao_id: UUID) -> dict:
    return assistente_servico.descartar_sessao(sessao_id)
