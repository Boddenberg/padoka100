from typing import Annotated

from fastapi import APIRouter, Depends

from app.modules.admin import seed_servico
from app.modules.admin.seed_esquemas import RequisicaoGerarVendasFake, RespostaGerarVendasFake
from app.modules.auth.dependencias import exigir_capacidade

router = APIRouter(prefix="/admin", tags=["admin"])
SeedGerar = Annotated[dict, Depends(exigir_capacidade("seed.gerar"))]


@router.post("/seed/vendas-fake", response_model=RespostaGerarVendasFake, status_code=201)
def gerar_vendas_fake(requisicao: RequisicaoGerarVendasFake, usuario: SeedGerar) -> dict:
    return seed_servico.gerar_vendas_fake(requisicao, usuario_autenticado=usuario)
