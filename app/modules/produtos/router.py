from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.modules.auth.dependencias import exigir_capacidade
from app.modules.midia import servico as servico_de_midia
from app.modules.midia.esquemas import MidiaSaida
from app.modules.produtos import servico
from app.modules.produtos.esquemas import (
    ProdutoListaSaida,
    ProdutoSaida,
    RequisicaoAtualizarProduto,
    RequisicaoCriarProduto,
    RequisicaoCriarVersaoDePreco,
    VersaoDePrecoSaida,
)

router = APIRouter(prefix="/produtos", tags=["produtos"])
CatalogoLer = Annotated[dict, Depends(exigir_capacidade("catalogo.ler"))]
CatalogoEditar = Annotated[dict, Depends(exigir_capacidade("catalogo.editar"))]


@router.get(
    "",
    response_model=list[ProdutoListaSaida],
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
)
def listar_produtos(
    usuario: CatalogoLer,
    somente_ativos: bool = True,
    data_preco: Annotated[date | None, Query()] = None,
) -> list[dict]:
    produtos = servico.listar_produtos(
        somente_ativos=somente_ativos,
        data_preco=data_preco,
        usuario_id=usuario["id"],
    )
    return servico.formatar_produtos_para_lista_http(produtos, somente_ativos=somente_ativos)


@router.post(
    "",
    response_model=ProdutoSaida,
    status_code=201,
)
def criar_produto(requisicao: RequisicaoCriarProduto, usuario: CatalogoEditar) -> dict:
    return servico.criar_produto(requisicao, usuario_id=usuario["id"])


@router.get("/{produto_id}", response_model=ProdutoSaida)
def buscar_produto(
    produto_id: UUID,
    usuario: CatalogoLer,
    data_preco: Annotated[date | None, Query()] = None,
) -> dict:
    return servico.buscar_produto(produto_id, data_preco=data_preco, usuario_id=usuario["id"])


@router.patch(
    "/{produto_id}",
    response_model=ProdutoSaida,
)
def atualizar_produto(
    produto_id: UUID,
    requisicao: RequisicaoAtualizarProduto,
    usuario: CatalogoEditar,
) -> dict:
    return servico.atualizar_produto(produto_id, requisicao, usuario_id=usuario["id"])


@router.get("/{produto_id}/precos", response_model=list[VersaoDePrecoSaida])
def listar_versoes_de_preco(produto_id: UUID, usuario: CatalogoLer) -> list[dict]:
    return servico.listar_versoes_de_preco(produto_id, usuario_id=usuario["id"])


@router.post(
    "/{produto_id}/precos",
    response_model=VersaoDePrecoSaida,
    status_code=201,
)
def criar_versao_de_preco(
    produto_id: UUID,
    requisicao: RequisicaoCriarVersaoDePreco,
    usuario: CatalogoEditar,
) -> dict:
    return servico.criar_versao_de_preco(produto_id, requisicao, usuario_id=usuario["id"])


@router.post(
    "/{produto_id}/midia",
    response_model=MidiaSaida,
    status_code=201,
)
async def enviar_midia_do_produto(
    produto_id: UUID,
    usuario: CatalogoEditar,
    file: Annotated[UploadFile, File()],
    descricao: Annotated[str | None, Form()] = None,
    texto_alternativo: Annotated[str | None, Form()] = None,
    definir_como_principal: Annotated[bool, Form()] = True,
) -> dict:
    return await servico_de_midia.enviar_midia(
        tipo_entidade="produto",
        entidade_id=produto_id,
        file=file,
        descricao=descricao,
        texto_alternativo=texto_alternativo,
        definir_como_principal=definir_como_principal,
        usuario_id=usuario["id"],
    )
