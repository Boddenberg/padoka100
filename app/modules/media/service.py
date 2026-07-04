import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import BadRequestError
from app.db.supabase import get_supabase_client
from app.shared.db import to_db_payload
from app.shared.timeline import record_timeline_event

OWNER_TYPES = {"product", "location", "sales_day", "sale", "ai_interaction"}


async def upload_media(
    *,
    owner_type: str,
    owner_id: UUID,
    file: UploadFile,
    description: str | None = None,
    alt_text: str | None = None,
    set_as_main: bool = False,
) -> dict:
    if owner_type not in OWNER_TYPES:
        raise BadRequestError("Tipo de dono de midia invalido.", {"owner_type": owner_type})

    content = await file.read()
    if not content:
        raise BadRequestError("Arquivo vazio.")

    settings = get_settings()
    client = get_supabase_client()
    bucket = settings.supabase_storage_bucket
    file_path = _build_file_path(owner_type, owner_id, file.filename)
    content_type = file.content_type or "application/octet-stream"

    client.storage.from_(bucket).upload(
        file_path,
        content,
        file_options={"content-type": content_type},
    )
    public_url = client.storage.from_(bucket).get_public_url(file_path)

    asset = (
        client.table("media_assets")
        .insert(
            to_db_payload(
                {
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "bucket": bucket,
                    "file_path": file_path,
                    "public_url": public_url,
                    "content_type": content_type,
                    "description": description,
                    "alt_text": alt_text,
                }
            )
        )
        .execute()
        .data[0]
    )

    if set_as_main and owner_type in {"product", "location"}:
        table = "products" if owner_type == "product" else "locations"
        client.table(table).update({"main_image_url": public_url}).eq("id", str(owner_id)).execute()

    record_timeline_event(
        client,
        event_type="media_uploaded",
        title="Midia enviada",
        entity_type=owner_type,
        entity_id=owner_id,
        details={
            "media_asset_id": asset["id"],
            "file_path": file_path,
            "content_type": content_type,
            "set_as_main": set_as_main,
        },
    )
    return asset


def _build_file_path(owner_type: str, owner_id: UUID, filename: str | None) -> str:
    suffix = Path(filename or "upload").suffix.lower()
    safe_stem = _safe_filename(Path(filename or "upload").stem)
    return f"{owner_type}/{owner_id}/{uuid4()}-{safe_stem}{suffix}"


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return safe or "arquivo"

