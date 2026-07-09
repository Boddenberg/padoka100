from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Path, UploadFile

from app.modules.midia import servico
from app.modules.midia.esquemas import MidiaSaida

router = APIRouter(prefix="/midia", tags=["midia"])


@router.post("/{tipo_entidade}/{entidade_id}", response_model=MidiaSaida, status_code=201)
async def enviar_midia(
    tipo_entidade: Annotated[
        str,
        Path(
            pattern=(
                "^(produto|local|dia_de_venda|venda|interacao_ia|usuario|"
                "sessao_custeio|notificacao)$"
            )
        ),
    ],
    entidade_id: Annotated[UUID, Path()],
    file: Annotated[UploadFile, File()],
    descricao: Annotated[str | None, Form()] = None,
    texto_alternativo: Annotated[str | None, Form()] = None,
    definir_como_principal: Annotated[bool, Form()] = False,
) -> dict:
    return await servico.enviar_midia(
        tipo_entidade=tipo_entidade,
        entidade_id=entidade_id,
        file=file,
        descricao=descricao,
        texto_alternativo=texto_alternativo,
        definir_como_principal=definir_como_principal,
    )
