from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile

from app.modules.ia import servico
from app.modules.ia.esquemas import (
    RequisicaoInterpretarComandoDeIA,
    RequisicaoInterpretarComandoDeVenda,
    RespostaConfirmarComandoDeIA,
    RespostaConfirmarVenda,
    RespostaInterpretarComandoDeIA,
    RespostaInterpretarComandoDeVenda,
    RespostaTranscreverAudioDeIA,
    RespostaTranscreverAudioDeVenda,
)

router = APIRouter(prefix="/ia", tags=["ia"])


@router.post("/interpretar-comando", response_model=RespostaInterpretarComandoDeIA)
def interpretar_comando(requisicao: RequisicaoInterpretarComandoDeIA) -> dict:
    return servico.interpretar_comando(requisicao)


@router.post("/interpretar-comando-de-venda", response_model=RespostaInterpretarComandoDeVenda)
def interpretar_comando_de_venda(requisicao: RequisicaoInterpretarComandoDeVenda) -> dict:
    return servico.interpretar_comando_de_venda(requisicao)


@router.post("/transcrever-audio", response_model=RespostaTranscreverAudioDeIA)
async def transcrever_audio(
    file: Annotated[UploadFile, File()],
    dia_de_venda_id: Annotated[UUID | None, Form()] = None,
    interpretar: Annotated[bool, Form()] = True,
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
) -> dict:
    return await servico.transcrever_audio_de_venda(
        file=file,
        dia_de_venda_id=dia_de_venda_id,
        interpretar=interpretar,
    )


@router.post("/interacoes/{interacao_ia_id}/confirmar", response_model=RespostaConfirmarComandoDeIA)
def confirmar_comando(interacao_ia_id: UUID) -> dict:
    return servico.confirmar_comando(interacao_ia_id)


@router.post("/interacoes/{interacao_ia_id}/confirmar-venda", response_model=RespostaConfirmarVenda)
def confirmar_venda(interacao_ia_id: UUID) -> dict:
    return servico.confirmar_venda(interacao_ia_id)
