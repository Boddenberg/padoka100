from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.modules.auth.dependencias import exigir_capacidade
from app.modules.ia import servico
from app.modules.ia.esquemas import (
    MidiaRecebidaPorIA,
    RequisicaoAnaliseEspecifica,
    RequisicaoAnalisePadrao,
    RequisicaoInterpretarComandoDeIA,
    RequisicaoInterpretarComandoDeVenda,
    RequisicaoRejeitarComandoDeIA,
    RespostaAnaliseIA,
    RespostaConfirmarComandoDeIA,
    RespostaConfirmarVenda,
    RespostaDadosEstruturadosIA,
    RespostaInterpretarComandoDeIA,
    RespostaInterpretarComandoDeVenda,
    RespostaRejeitarComandoDeIA,
    RespostaTranscreverAudioDeIA,
    RespostaTranscreverAudioDeVenda,
    ThreadIA,
)

router = APIRouter(prefix="/ia", tags=["ia"])
IaOperacional = Annotated[dict, Depends(exigir_capacidade("ia.operacional"))]
IaAnalitica = Annotated[dict, Depends(exigir_capacidade("ia.analitica"))]
IaTroubleshooting = Annotated[dict, Depends(exigir_capacidade("admin.gerenciar"))]


@router.get(
    "/dados-estruturados/periodo",
    response_model=RespostaDadosEstruturadosIA,
)
def montar_dados_estruturados_periodo(
    data_inicio: str,
    data_fim: str,
    usuario: IaAnalitica,
    produto_id: UUID | None = None,
) -> dict:
    return servico.montar_dados_estruturados_periodo(
        data_inicio=data_inicio,
        data_fim=data_fim,
        produto_id=produto_id,
        usuario_id=usuario["id"],
    )


@router.get("/midias-recebidas", response_model=list[MidiaRecebidaPorIA])
def listar_midias_recebidas(
    _: IaTroubleshooting,
    item: Annotated[str | None, Query(pattern="^(audio|foto)$")] = None,
    thread_id: Annotated[UUID | None, Query()] = None,
    usuario_id: Annotated[UUID | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict]:
    return servico.listar_midias_recebidas_por_ia(
        item=item,
        thread_id=thread_id,
        usuario_id=usuario_id,
        limite=limite,
    )


@router.get("/threads", response_model=list[ThreadIA])
def listar_threads_de_ia(
    _: IaTroubleshooting,
    thread_id: Annotated[UUID | None, Query()] = None,
    usuario_id: Annotated[UUID | None, Query()] = None,
    situacao: Annotated[
        str | None,
        Query(pattern="^(interpretada|confirmada|rejeitada|falhou)$"),
    ] = None,
    limite_threads: Annotated[int, Query(ge=1, le=100)] = 50,
    limite_interacoes: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[dict]:
    return servico.listar_threads_de_ia(
        thread_id=thread_id,
        usuario_id=usuario_id,
        situacao=situacao,
        limite_threads=limite_threads,
        limite_interacoes=limite_interacoes,
    )


@router.post(
    "/analises/padrao",
    response_model=RespostaAnaliseIA,
)
def analisar_periodo_padrao(requisicao: RequisicaoAnalisePadrao, usuario: IaAnalitica) -> dict:
    return servico.analisar_periodo_padrao(requisicao, usuario_id=usuario["id"])


@router.post(
    "/analises/especifica",
    response_model=RespostaAnaliseIA,
)
def analisar_periodo_especifico(
    requisicao: RequisicaoAnaliseEspecifica,
    usuario: IaAnalitica,
) -> dict:
    return servico.analisar_periodo_especifico(requisicao, usuario_id=usuario["id"])


@router.post("/interpretar-comando", response_model=RespostaInterpretarComandoDeIA)
def interpretar_comando(
    requisicao: RequisicaoInterpretarComandoDeIA,
    usuario: IaOperacional,
) -> dict:
    return servico.interpretar_comando(requisicao, usuario_id=usuario["id"])


@router.post("/interpretar-comando-de-venda", response_model=RespostaInterpretarComandoDeVenda)
def interpretar_comando_de_venda(
    requisicao: RequisicaoInterpretarComandoDeVenda,
    usuario: IaOperacional,
) -> dict:
    return servico.interpretar_comando_de_venda(requisicao, usuario_id=usuario["id"])


@router.post("/transcrever-audio", response_model=RespostaTranscreverAudioDeIA)
async def transcrever_audio(
    file: Annotated[UploadFile, File()],
    usuario: IaOperacional,
    dia_de_venda_id: Annotated[UUID | None, Form()] = None,
    interpretar: Annotated[bool, Form()] = True,
    thread_id: Annotated[UUID | None, Form()] = None,
) -> dict:
    return await servico.transcrever_audio(
        file=file,
        dia_de_venda_id=dia_de_venda_id,
        interpretar=interpretar,
        thread_id=thread_id,
        usuario_id=usuario["id"],
        usuario_nome=usuario.get("nome"),
    )


@router.post("/transcrever-audio-de-venda", response_model=RespostaTranscreverAudioDeVenda)
async def transcrever_audio_de_venda(
    file: Annotated[UploadFile, File()],
    usuario: IaOperacional,
    dia_de_venda_id: Annotated[UUID | None, Form()] = None,
    interpretar: Annotated[bool, Form()] = True,
    thread_id: Annotated[UUID | None, Form()] = None,
) -> dict:
    return await servico.transcrever_audio_de_venda(
        file=file,
        dia_de_venda_id=dia_de_venda_id,
        interpretar=interpretar,
        thread_id=thread_id,
        usuario_id=usuario["id"],
        usuario_nome=usuario.get("nome"),
    )


@router.post("/produtos/importar-cardapio", response_model=RespostaInterpretarComandoDeIA)
async def importar_cardapio_por_imagem(
    file: Annotated[UploadFile, File()],
    usuario: IaOperacional,
    contexto: Annotated[str | None, Form()] = None,
    thread_id: Annotated[UUID | None, Form()] = None,
) -> dict:
    return await servico.importar_cardapio_por_imagem(
        file=file,
        contexto=contexto,
        thread_id=thread_id,
        usuario_id=usuario["id"],
        usuario_nome=usuario.get("nome"),
    )


@router.post("/producao/importar-foto", response_model=RespostaInterpretarComandoDeIA)
async def importar_producao_por_imagem(
    file: Annotated[UploadFile, File()],
    usuario: IaOperacional,
    dia_de_venda_id: Annotated[UUID | None, Form()] = None,
    contexto: Annotated[str | None, Form()] = None,
    thread_id: Annotated[UUID | None, Form()] = None,
) -> dict:
    return await servico.importar_producao_por_imagem(
        file=file,
        dia_de_venda_id=dia_de_venda_id,
        contexto=contexto,
        thread_id=thread_id,
        usuario_id=usuario["id"],
        usuario_nome=usuario.get("nome"),
    )


@router.post("/interacoes/{interacao_ia_id}/confirmar", response_model=RespostaConfirmarComandoDeIA)
def confirmar_comando(interacao_ia_id: UUID, usuario: IaOperacional) -> dict:
    return servico.confirmar_comando(interacao_ia_id, usuario_id=usuario["id"])


@router.post("/interacoes/{interacao_ia_id}/confirmar-venda", response_model=RespostaConfirmarVenda)
def confirmar_venda(interacao_ia_id: UUID, usuario: IaOperacional) -> dict:
    return servico.confirmar_venda(interacao_ia_id, usuario_id=usuario["id"])


@router.post(
    "/interacoes/{interacao_ia_id}/rejeitar",
    response_model=RespostaRejeitarComandoDeIA,
)
def rejeitar_comando(
    interacao_ia_id: UUID,
    requisicao: RequisicaoRejeitarComandoDeIA,
    usuario: IaOperacional,
) -> dict:
    return servico.rejeitar_comando(
        interacao_ia_id,
        motivo=requisicao.motivo,
        usuario_id=usuario["id"],
    )
