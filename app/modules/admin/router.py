from typing import Annotated

from fastapi import APIRouter, Depends

from app.modules.admin import seed_servico
from app.modules.admin.dependencias import exigir_admin_real
from app.modules.admin.seed_esquemas import RequisicaoGerarVendasFake, RespostaGerarVendasFake

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/seed/vendas-fake", response_model=RespostaGerarVendasFake, status_code=201)
def gerar_vendas_fake(
    requisicao: RequisicaoGerarVendasFake,
    _: Annotated[dict, Depends(exigir_admin_real)],
) -> dict:
    return seed_servico.gerar_vendas_fake(requisicao)
