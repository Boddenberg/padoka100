from datetime import datetime
from uuid import UUID

from app.shared.schemas import ApiModel


class MediaAssetOut(ApiModel):
    id: UUID
    owner_type: str
    owner_id: UUID
    bucket: str
    file_path: str
    public_url: str | None = None
    content_type: str | None = None
    description: str | None = None
    alt_text: str | None = None
    created_at: datetime

