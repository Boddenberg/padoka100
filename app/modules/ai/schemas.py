from uuid import UUID

from pydantic import Field

from app.modules.sales.schemas import SaleOut
from app.shared.schemas import ApiModel


class InterpretSaleCommandRequest(ApiModel):
    text: str = Field(min_length=1)
    sales_day_id: UUID | None = None
    allow_fallback: bool = True


class InterpretedSaleItem(ApiModel):
    product_id: UUID
    product_name: str
    quantity: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)


class InterpretSaleCommandResponse(ApiModel):
    ai_interaction_id: UUID
    action: str
    needs_confirmation: bool = True
    assistant_message: str
    items: list[InterpretedSaleItem] = Field(default_factory=list)
    unmatched_items: list[str] = Field(default_factory=list)
    confirmation_payload: dict
    used_model: str


class TranscribeSaleAudioResponse(ApiModel):
    transcript: str
    audio_url: str | None = None
    interpretation: InterpretSaleCommandResponse | None = None


class ConfirmSaleResponse(ApiModel):
    ai_interaction_id: UUID
    sale: SaleOut

