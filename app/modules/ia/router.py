from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.modules.auth.dependencias import exigir_capacidade
from app.modules.ia import servico
from app.modules.ia.esquemas import (
    RequisicaoAnaliseEspecifica,
    RequisicaoAnalisePadrao,
    RequisicaoInterpretarComandoDeIA,
    RequisicaoInterpretarComandoDeVenda,
    RespostaAnaliseIA,
    RespostaConfirmarComandoDeIA,
    RespostaConfirmarVenda,
    RespostaDadosEstruturadosIA,
    RespostaInterpretarComandoDeIA,
    RespostaInterpretarComandoDeVenda,
    RespostaTranscreverAudioDeIA,
    RespostaTranscreverAudioDeVenda,
)

router = APIRouter(prefix="/ia", tags=["ia"])
IaOperacional = Annotated[dict, Depends(exigir_capacidade("ia.operacional"))]
IaAnalitica = Annotated[dict, Depends(exigir_capacidade("ia.analitica"))]


@router.get(
    "/dados-estruturados/periodo",
    response_model=RespostaDadosEstruturadosIA,
)
def montar_dados_estruturados_periodo(
    data_inicio: str,
    data_fim: str,
    produto_id: UUID | None = None,
    _: IaAnalitica = None,
) -> dict:
    return servico.montar_dados_estruturados_periodo(
        data_inicio=data_inicio,
        data_fim=data_fim,
        produto_id=produto_id,
    )


@router.post(
    "/analises/padrao",
    response_model=RespostaAnaliseIA,
)
def analisar_periodo_padrao(requisicao: RequisicaoAnalisePadrao, _: IaAnalitica = None) -> dict:
    return servico.analisar_periodo_padrao(requisicao)


@router.post(
    "/analises/especifica",
    response_model=RespostaAnaliseIA,
)
def analisar_periodo_especifico(
    requisicao: RequisicaoAnaliseEspecifica,
    _: IaAnalitica = None,
) -> dict:
    return servico.analisar_periodo_especifico(requisicao)


@router.post("/interpretar-comando", response_model=RespostaInterpretarComandoDeIA)
def interpretar_comando(
    requisicao: RequisicaoInterpretarComandoDeIA,
    _: IaOperacional = None,
) -> dict:
    return servico.interpretar_comando(requisicao)


@router.post("/interpretar-comando-de-venda", response_model=RespostaInterpretarComandoDeVenda)
def interpretar_comando_de_venda(
    requisicao: RequisicaoInterpretarComandoDeVenda,
    _: IaOperacional = None,
) -> dict:
    return servico.interpretar_comando_de_venda(requisicao)


@router.post("/transcrever-audio", response_model=RespostaTranscreverAudioDeIA)
async def transcrever_audio(
    file: Annotated[UploadFile, File()],
    dia_de_venda_id: Annotated[UUID | None, Form()] = None,
    interpretar: Annotated[bool, Form()] = True,
    _: IaOperacional = None,
) -> dict:
    return await servico.transcrever_audio(
        file=file,
        dia_de_venda_id=dia_de_venda_id,
        interpretar=interpretar,
    )


@router.post("/transcrever-audio-de-venda", response_model=RespostaTranscreverAudioDeVenda)
async def transcrever_audio_de_venda(
    file: Annotated[UploadFile, File()],
    dia_de_venda_id: Annotated[UUID | None, Form()] = None,
    interpretar: Annotated[bool, Form()] = True,
    _: IaOperacional = None,
) -> dict:
    return await servico.transcrever_audio_de_venda(
        file=file,
        dia_de_venda_id=dia_de_venda_id,
        interpretar=interpretar,
    )


@router.post("/interacoes/{interacao_ia_id}/confirmar", response_model=RespostaConfirmarComandoDeIA)
def confirmar_comando(interacao_ia_id: UUID, _: IaOperacional = None) -> dict:
    return servico.confirmar_comando(interacao_ia_id)


@router.post("/interacoes/{interacao_ia_id}/confirmar-venda", response_model=RespostaConfirmarVenda)
def confirmar_venda(interacao_ia_id: UUID, _: IaOperacional = None) -> dict:
    return servico.confirmar_venda(interacao_ia_id)
