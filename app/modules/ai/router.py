from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile

from app.modules.ai import service
from app.modules.ai.schemas import (
    ConfirmSaleResponse,
    InterpretSaleCommandRequest,
    InterpretSaleCommandResponse,
    TranscribeSaleAudioResponse,
)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/interpret-sale-command", response_model=InterpretSaleCommandResponse)
def interpret_sale_command(payload: InterpretSaleCommandRequest) -> dict:
    return service.interpret_sale_command(payload)


@router.post("/transcribe-sale-audio", response_model=TranscribeSaleAudioResponse)
async def transcribe_sale_audio(
    file: UploadFile = File(...),
    sales_day_id: UUID | None = Form(default=None),
    interpret: bool = Form(default=True),
) -> dict:
    return await service.transcribe_sale_audio(
        file=file,
        sales_day_id=sales_day_id,
        interpret=interpret,
    )


@router.post("/interactions/{ai_interaction_id}/confirm-sale", response_model=ConfirmSaleResponse)
def confirm_sale(ai_interaction_id: UUID) -> dict:
    return service.confirm_sale(ai_interaction_id)

