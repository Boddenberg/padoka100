from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile

from app.modules.ia import servico
from app.modules.ia.esquemas import (
    RequisicaoInterpretarComandoDeVenda,
    RespostaConfirmarVenda,
    RespostaInterpretarComandoDeVenda,
    RespostaTranscreverAudioDeVenda,
)

router = APIRouter(prefix="/ia", tags=["ia"])


@router.post("/interpretar-comando-de-venda", response_model=RespostaInterpretarComandoDeVenda)
def interpretar_comando_de_venda(requisicao: RequisicaoInterpretarComandoDeVenda) -> dict:
    return servico.interpretar_comando_de_venda(requisicao)


@router.post("/transcrever-audio-de-venda", response_model=RespostaTranscreverAudioDeVenda)
async def transcrever_audio_de_venda(
    file: UploadFile = File(...),
    dia_de_venda_id: UUID | None = Form(default=None),
    interpretar: bool = Form(default=True),
) -> dict:
    return await servico.transcrever_audio_de_venda(
        file=file,
        dia_de_venda_id=dia_de_venda_id,
        interpretar=interpretar,
    )


@router.post("/interacoes/{interacao_ia_id}/confirmar-venda", response_model=RespostaConfirmarVenda)
def confirmar_venda(interacao_ia_id: UUID) -> dict:
    return servico.confirmar_venda(interacao_ia_id)

