from uuid import UUID

from fastapi import APIRouter, File, Form, Path, UploadFile

from app.modules.midia import servico
from app.modules.midia.esquemas import MidiaSaida

router = APIRouter(prefix="/midia", tags=["midia"])


@router.post("/{tipo_entidade}/{entidade_id}", response_model=MidiaSaida, status_code=201)
async def enviar_midia(
    tipo_entidade: str = Path(..., pattern="^(produto|local|dia_de_venda|venda|interacao_ia)$"),
    entidade_id: UUID = Path(...),
    file: UploadFile = File(...),
    descricao: str | None = Form(default=None),
    texto_alternativo: str | None = Form(default=None),
    definir_como_principal: bool = Form(default=False),
) -> dict:
    return await servico.enviar_midia(
        tipo_entidade=tipo_entidade,
        entidade_id=entidade_id,
        file=file,
        descricao=descricao,
        texto_alternativo=texto_alternativo,
        definir_como_principal=definir_como_principal,
    )
