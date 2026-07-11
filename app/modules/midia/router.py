from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile

from app.core.errors import AppError
from app.modules.auth.dependencias import exigir_capacidade
from app.modules.auth.domain.capacidades import usuario_tem_capacidade
from app.modules.midia import servico
from app.modules.midia.esquemas import MidiaSaida

router = APIRouter(prefix="/midia", tags=["midia"])
MidiaEnviar = Annotated[dict, Depends(exigir_capacidade("midia.enviar"))]


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
    usuario: MidiaEnviar,
    descricao: Annotated[str | None, Form()] = None,
    texto_alternativo: Annotated[str | None, Form()] = None,
    definir_como_principal: Annotated[bool, Form()] = False,
) -> dict:
    if tipo_entidade == "notificacao" and not usuario_tem_capacidade(
        usuario, "notificacoes.admin"
    ):
        raise AppError(
            status_code=403,
            code="forbidden",
            message="Somente administradores anexam midia a notificacoes.",
            details={"capacidade_necessaria": "notificacoes.admin"},
        )
    return await servico.enviar_midia(
        tipo_entidade=tipo_entidade,
        entidade_id=entidade_id,
        file=file,
        descricao=descricao,
        texto_alternativo=texto_alternativo,
        definir_como_principal=definir_como_principal,
        usuario_id=usuario["id"],
    )
