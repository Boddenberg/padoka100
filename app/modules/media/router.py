from uuid import UUID

from fastapi import APIRouter, File, Form, Path, UploadFile

from app.modules.media import service
from app.modules.media.schemas import MediaAssetOut

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/{owner_type}/{owner_id}", response_model=MediaAssetOut, status_code=201)
async def upload_media(
    owner_type: str = Path(..., pattern="^(product|location|sales_day|sale|ai_interaction)$"),
    owner_id: UUID = Path(...),
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    alt_text: str | None = Form(default=None),
    set_as_main: bool = Form(default=False),
) -> dict:
    return await service.upload_media(
        owner_type=owner_type,
        owner_id=owner_id,
        file=file,
        description=description,
        alt_text=alt_text,
        set_as_main=set_as_main,
    )

