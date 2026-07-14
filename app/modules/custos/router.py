from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.modules.auth.dependencias import exigir_capacidade
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
CustosUsar = Annotated[dict, Depends(exigir_capacidade("custos.usar"))]
ComprasUsar = Annotated[dict, Depends(exigir_capacidade("compras.usar"))]
AssistenteCusteio = Annotated[dict, Depends(exigir_capacidade("custos.assistente"))]


@router.get("/insumos", response_model=list[InsumoSaida])
def listar_insumos(usuario: CustosUsar) -> list[dict]:
    return servico.listar_insumos(usuario_id=usuario["id"])


@router.post("/insumos", response_model=InsumoSaida, status_code=201)
def criar_insumo(requisicao: RequisicaoCriarInsumo, usuario: CustosUsar) -> dict:
    return servico.criar_insumo(requisicao, usuario_id=usuario["id"])


@router.patch("/insumos/{insumo_id}", response_model=InsumoSaida)
def atualizar_insumo(
    insumo_id: UUID,
    requisicao: RequisicaoAtualizarInsumo,
    usuario: CustosUsar,
) -> dict:
    return servico.atualizar_insumo(insumo_id, requisicao, usuario_id=usuario["id"])


@router.get("/insumos/{insumo_id}/precos", response_model=list[InsumoPrecoSaida])
def listar_precos_insumo(insumo_id: UUID, usuario: CustosUsar) -> list[dict]:
    return servico.listar_precos_insumo(insumo_id, usuario_id=usuario["id"])


@router.post("/insumos/{insumo_id}/precos", response_model=InsumoSaida, status_code=201)
def registrar_preco_insumo(
    insumo_id: UUID,
    requisicao: RequisicaoRegistrarPrecoInsumo,
    usuario: CustosUsar,
) -> dict:
    return servico.registrar_preco_insumo(insumo_id, requisicao, usuario_id=usuario["id"])[
        "insumo"
    ]


@router.post(
    "/compras/atualizar-precos",
    response_model=RespostaAtualizarPrecosPorCompra,
)
def atualizar_precos_por_compra(
    requisicao: RequisicaoAtualizarPrecosPorCompra,
    usuario: CustosUsar,
) -> dict:
    return servico.atualizar_precos_por_compra(requisicao, usuario_id=usuario["id"])


@router.post(
    "/compras/nota/atualizar-precos",
    response_model=RespostaAtualizarPrecosPorCompra,
)
async def atualizar_precos_por_nota_arquivo(
    file: Annotated[UploadFile, File()],
    usuario: AssistenteCusteio,
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
        usuario_id=usuario["id"],
        usuario_nome=usuario.get("nome"),
    )


@router.get("/produtos-com-receita", response_model=list[ProdutoComReceitaSaida])
def listar_produtos_com_receita(usuario: CustosUsar) -> list[dict]:
    return servico.listar_produtos_com_receita(usuario_id=usuario["id"])


@router.get("/produtos/{produto_id}/receitas", response_model=list[ReceitaSaida])
def listar_receitas_do_produto(produto_id: UUID, usuario: CustosUsar) -> list[dict]:
    return servico.listar_receitas_do_produto(produto_id, usuario_id=usuario["id"])


@router.post("/produtos/{produto_id}/receitas", response_model=ReceitaSaida, status_code=201)
def criar_receita(
    produto_id: UUID,
    requisicao: RequisicaoCriarReceita,
    usuario: CustosUsar,
) -> dict:
    return servico.criar_receita(produto_id, requisicao, usuario_id=usuario["id"])


@router.post(
    "/produtos/{produto_id}/custos-adicionais",
    response_model=CustoAdicionalSaida,
    status_code=201,
)
def criar_custo_adicional(
    produto_id: UUID,
    requisicao: RequisicaoCriarCustoAdicional,
    usuario: CustosUsar,
) -> dict:
    return servico.criar_custo_adicional(produto_id, requisicao, usuario_id=usuario["id"])


@router.get("/produtos/{produto_id}/calculo", response_model=CalculoCustoProdutoSaida)
def calcular_custo_do_produto(
    produto_id: UUID,
    usuario: CustosUsar,
    receita_id: Annotated[UUID | None, Query()] = None,
    data_referencia: Annotated[date | None, Query()] = None,
) -> dict:
    return servico.calcular_custo_do_produto(
        produto_id,
        receita_id=receita_id,
        data_referencia=data_referencia,
        usuario_id=usuario["id"],
    )


@router.post("/lista-compras", response_model=ListaComprasSaida)
def gerar_lista_compras(requisicao: RequisicaoGerarListaCompras, usuario: ComprasUsar) -> dict:
    return servico.gerar_lista_compras(requisicao, usuario_id=usuario["id"])


@router.get("/listas-compras", response_model=list[ListaComprasSaida])
def listar_listas_compras(
    usuario: ComprasUsar,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict]:
    return servico.listar_listas_compras(limite=limite, usuario_id=usuario["id"])


@router.get("/listas-compras/{lista_id}", response_model=ListaComprasSaida)
def buscar_lista_compras(lista_id: UUID, usuario: ComprasUsar) -> dict:
    return servico.buscar_lista_compras(lista_id, usuario_id=usuario["id"])


@router.post("/assistente/sessoes", response_model=SessaoCusteioSaida, status_code=201)
def criar_sessao_de_custeio(
    requisicao: RequisicaoCriarSessaoCusteio,
    usuario: AssistenteCusteio,
) -> dict:
    return assistente_servico.criar_sessao(requisicao, usuario_id=usuario["id"])


@router.get("/assistente/sessoes/{sessao_id}", response_model=SessaoCusteioSaida)
def buscar_sessao_de_custeio(sessao_id: UUID, usuario: AssistenteCusteio) -> dict:
    return assistente_servico.buscar_sessao(sessao_id, usuario_id=usuario["id"])


@router.get(
    "/assistente/produtos/{produto_id}/sessao",
    response_model=SessaoCusteioSaida | None,
)
def buscar_sessao_de_custeio_do_produto(
    produto_id: UUID, usuario: AssistenteCusteio
) -> dict | None:
    return assistente_servico.buscar_sessao_do_produto(produto_id, usuario_id=usuario["id"])


@router.post(
    "/assistente/sessoes/{sessao_id}/entradas/texto",
    response_model=SessaoCusteioSaida,
)
def adicionar_texto_ao_custeio(
    sessao_id: UUID,
    requisicao: RequisicaoEntradaTextoCusteio,
    usuario: AssistenteCusteio,
) -> dict:
    return assistente_servico.adicionar_entrada_texto(
        sessao_id,
        requisicao,
        usuario_id=usuario["id"],
    )


@router.post(
    "/assistente/sessoes/{sessao_id}/entradas/formulario",
    response_model=SessaoCusteioSaida,
)
def adicionar_formulario_ao_custeio(
    sessao_id: UUID,
    requisicao: RequisicaoEntradaFormularioCusteio,
    usuario: AssistenteCusteio,
) -> dict:
    return assistente_servico.adicionar_entrada_formulario(
        sessao_id,
        requisicao,
        usuario_id=usuario["id"],
    )


@router.post(
    "/assistente/sessoes/{sessao_id}/entradas/arquivo",
    response_model=SessaoCusteioSaida,
)
async def adicionar_arquivo_ao_custeio(
    sessao_id: UUID,
    file: Annotated[UploadFile, File()],
    tipo: Annotated[str, Form(pattern="^(audio|imagem)$")],
    usuario: AssistenteCusteio,
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
        usuario_id=usuario["id"],
        usuario_nome=usuario.get("nome"),
    )


@router.patch(
    "/assistente/sessoes/{sessao_id}/rascunho",
    response_model=SessaoCusteioSaida,
)
def atualizar_rascunho_de_custeio(
    sessao_id: UUID,
    requisicao: RequisicaoAtualizarRascunhoCusteio,
    usuario: AssistenteCusteio,
) -> dict:
    return assistente_servico.atualizar_rascunho(sessao_id, requisicao, usuario_id=usuario["id"])


@router.post(
    "/assistente/sessoes/{sessao_id}/confirmar",
    response_model=SessaoCusteioSaida,
)
def confirmar_sessao_de_custeio(
    sessao_id: UUID,
    requisicao: RequisicaoConfirmarSessaoCusteio,
    usuario: AssistenteCusteio,
) -> dict:
    return assistente_servico.confirmar_sessao(sessao_id, requisicao, usuario_id=usuario["id"])


@router.post(
    "/assistente/sessoes/{sessao_id}/descartar",
    response_model=SessaoCusteioSaida,
)
def descartar_sessao_de_custeio(sessao_id: UUID, usuario: AssistenteCusteio) -> dict:
    return assistente_servico.descartar_sessao(sessao_id, usuario_id=usuario["id"])
