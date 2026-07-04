import io
import json
import re
import unicodedata
from uuid import UUID

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import BadRequestError, MissingConfigurationError, NotFoundError
from app.db.openai import get_openai_client
from app.db.supabase import get_supabase_client
from app.modules.ai.schemas import InterpretSaleCommandRequest
from app.modules.media.service import upload_media_bytes
from app.modules.products import service as products_service
from app.modules.sales import service as sales_service
from app.modules.sales.schemas import SaleCreate
from app.shared.db import first_or_none, to_db_payload

NUMBER_WORDS = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "três": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "quatorze": 14,
    "catorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
}
IGNORED_PRODUCT_TOKENS = {"pao", "paes", "de", "do", "da", "recheado", "recheada"}


def interpret_sale_command(
    payload: InterpretSaleCommandRequest,
    *,
    input_type: str = "text",
    audio_url: str | None = None,
) -> dict:
    settings = get_settings()
    products = products_service.list_products(active_only=True)
    if not products:
        raise BadRequestError("Cadastre produtos antes de usar a interpretacao de vendas.")

    used_model = "fallback-parser"
    if settings.openai_text_configured:
        try:
            interpretation = _interpret_with_openai(payload.text, products)
            used_model = settings.openai_text_model
        except Exception:
            if not payload.allow_fallback:
                raise
            interpretation = _interpret_with_fallback(payload.text, products)
    else:
        interpretation = _interpret_with_fallback(payload.text, products)

    confirmation_payload = _build_confirmation_payload(
        interpretation=interpretation,
        sales_day_id=payload.sales_day_id,
        raw_text=payload.text,
        input_type="audio" if input_type == "audio" else "ai",
    )
    interaction = _create_ai_interaction(
        sales_day_id=payload.sales_day_id,
        input_type=input_type,
        raw_text=payload.text,
        audio_url=audio_url,
        interpreted_action=interpretation,
        confirmation_payload=confirmation_payload,
    )
    confirmation_payload["ai_interaction_id"] = interaction["id"]
    if confirmation_payload.get("sale"):
        confirmation_payload["sale"]["ai_interaction_id"] = interaction["id"]
    get_supabase_client().table("ai_interactions").update(
        to_db_payload({"confirmation_payload": confirmation_payload})
    ).eq("id", interaction["id"]).execute()

    return {
        "ai_interaction_id": interaction["id"],
        "action": interpretation["action"],
        "needs_confirmation": True,
        "assistant_message": interpretation["assistant_message"],
        "items": interpretation["items"],
        "unmatched_items": interpretation["unmatched_items"],
        "confirmation_payload": confirmation_payload,
        "used_model": used_model,
    }


async def transcribe_sale_audio(
    *,
    file: UploadFile,
    sales_day_id: UUID | None = None,
    interpret: bool = True,
) -> dict:
    settings = get_settings()
    missing = []
    if not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not settings.openai_transcription_model:
        missing.append("OPENAI_TRANSCRIPTION_MODEL")
    if missing:
        raise MissingConfigurationError("OpenAI Audio", missing)

    content = await file.read()
    if not content:
        raise BadRequestError("Arquivo de audio vazio.")

    audio_buffer = io.BytesIO(content)
    audio_buffer.name = file.filename or "audio.webm"
    transcription = get_openai_client().audio.transcriptions.create(
        model=settings.openai_transcription_model,
        file=audio_buffer,
    )
    transcript = getattr(transcription, "text", None) or transcription.get("text", "")
    interpretation = None
    audio_url = None

    if interpret:
        interpretation = interpret_sale_command(
            InterpretSaleCommandRequest(text=transcript, sales_day_id=sales_day_id),
            input_type="audio",
        )
        asset = upload_media_bytes(
            owner_type="ai_interaction",
            owner_id=UUID(interpretation["ai_interaction_id"]),
            content=content,
            filename=file.filename,
            content_type=file.content_type,
            description="Audio usado para registrar venda",
        )
        audio_url = asset.get("public_url")
        confirmation_payload = interpretation["confirmation_payload"]
        if confirmation_payload.get("sale"):
            confirmation_payload["sale"]["audio_url"] = audio_url
        interpretation["confirmation_payload"] = confirmation_payload
        get_supabase_client().table("ai_interactions").update(
            to_db_payload({"audio_url": audio_url, "confirmation_payload": confirmation_payload})
        ).eq("id", interpretation["ai_interaction_id"]).execute()
    return {
        "transcript": transcript,
        "audio_url": audio_url,
        "interpretation": interpretation,
    }


def confirm_sale(ai_interaction_id: UUID) -> dict:
    client = get_supabase_client()
    interaction = first_or_none(
        client.table("ai_interactions")
        .select("*")
        .eq("id", str(ai_interaction_id))
        .limit(1)
        .execute()
        .data
    )
    if not interaction:
        raise NotFoundError("Interacao de IA", str(ai_interaction_id))
    if interaction["status"] == "confirmed":
        raise BadRequestError("Essa interacao de IA ja foi confirmada.")

    confirmation_payload = interaction.get("confirmation_payload") or {}
    sale_payload = confirmation_payload.get("sale")
    if not sale_payload:
        raise BadRequestError("Essa interacao nao tem uma venda pronta para confirmar.")

    sale = sales_service.create_sale(SaleCreate(**sale_payload))
    client.table("ai_interactions").update({"status": "confirmed"}).eq(
        "id", str(ai_interaction_id)
    ).execute()
    return {"ai_interaction_id": ai_interaction_id, "sale": sale}


def _interpret_with_openai(text: str, products: list[dict]) -> dict:
    settings = get_settings()
    catalog = [
        {
            "id": product["id"],
            "name": product["name"],
            "description": product.get("description"),
            "visual_description": product.get("visual_description"),
        }
        for product in products
    ]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["action", "items", "unmatched_items", "assistant_message"],
        "properties": {
            "action": {"type": "string", "enum": ["register_sale", "unknown"]},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["product_id", "product_name", "quantity", "confidence"],
                    "properties": {
                        "product_id": {"type": "string"},
                        "product_name": {"type": "string"},
                        "quantity": {"type": "integer", "minimum": 1},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
            "unmatched_items": {"type": "array", "items": {"type": "string"}},
            "assistant_message": {"type": "string"},
        },
    }
    response = get_openai_client().responses.create(
        model=settings.openai_text_model,
        instructions=(
            "Voce interpreta comandos curtos de venda para um padeiro. "
            "Use apenas produtos do catalogo. Nao invente produto. "
            "Se faltar certeza, coloque em unmatched_items."
        ),
        input=(
            "Catalogo de produtos:\n"
            f"{json.dumps(catalog, ensure_ascii=False)}\n\n"
            f"Comando falado ou digitado: {text}"
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "sale_command_interpretation",
                "schema": schema,
                "strict": True,
            }
        },
    )
    return json.loads(response.output_text)


def _interpret_with_fallback(text: str, products: list[dict]) -> dict:
    normalized_text = _normalize(text)
    tokens = normalized_text.split()
    items = []
    unmatched_items = []

    for product in products:
        product_tokens = [
            token
            for token in _normalize(product["name"]).split()
            if token not in IGNORED_PRODUCT_TOKENS
        ]
        if not product_tokens or not all(token in tokens for token in product_tokens):
            continue
        first_position = min(tokens.index(token) for token in product_tokens)
        quantity = _find_quantity_before(tokens, first_position)
        items.append(
            {
                "product_id": product["id"],
                "product_name": product["name"],
                "quantity": quantity,
                "confidence": 0.65,
            }
        )

    action = "register_sale" if items else "unknown"
    if not items:
        unmatched_items.append(text)
    return {
        "action": action,
        "items": items,
        "unmatched_items": unmatched_items,
        "assistant_message": (
            "Confira antes de salvar a venda."
            if items
            else "Nao consegui identificar nenhum produto cadastrado nesse comando."
        ),
    }


def _build_confirmation_payload(
    *,
    interpretation: dict,
    sales_day_id: UUID | None,
    raw_text: str,
    input_type: str,
) -> dict:
    sale_payload = None
    if interpretation["action"] == "register_sale" and sales_day_id and interpretation["items"]:
        sale_payload = {
            "sales_day_id": str(sales_day_id),
            "input_type": input_type,
            "raw_text": raw_text,
            "items": [
                {"product_id": item["product_id"], "quantity": item["quantity"]}
                for item in interpretation["items"]
            ],
        }
    return {
        "action": interpretation["action"],
        "needs_confirmation": True,
        "sale": sale_payload,
    }


def _create_ai_interaction(
    *,
    sales_day_id: UUID | None,
    input_type: str,
    raw_text: str,
    audio_url: str | None,
    interpreted_action: dict,
    confirmation_payload: dict,
) -> dict:
    return (
        get_supabase_client()
        .table("ai_interactions")
        .insert(
            to_db_payload(
                {
                    "sales_day_id": sales_day_id,
                    "input_type": input_type,
                    "raw_text": raw_text,
                    "audio_url": audio_url,
                    "interpreted_action": interpreted_action,
                    "confirmation_payload": confirmation_payload,
                    "status": "interpreted",
                }
            )
        )
        .execute()
        .data[0]
    )


def _find_quantity_before(tokens: list[str], position: int) -> int:
    window = tokens[max(0, position - 6) : position]
    for token in reversed(window):
        if token.isdigit():
            return max(int(token), 1)
        if token in NUMBER_WORDS:
            return NUMBER_WORDS[token]
        match = re.match(r"(\d+)x?", token)
        if match:
            return max(int(match.group(1)), 1)
    return 1


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value).strip()
