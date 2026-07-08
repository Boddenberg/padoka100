from fastapi import APIRouter

from app.modules.auth.router import router as router_de_auth
from app.modules.custos.router import router as router_de_custos
from app.modules.dias_de_venda.router import router as router_de_dias_de_venda
from app.modules.historico.router import router as router_de_historico
from app.modules.ia.router import router as router_de_ia
from app.modules.locais.router import router as router_de_locais
from app.modules.midia.router import router as router_de_midia
from app.modules.produtos.router import router as router_de_produtos
from app.modules.relatorios.router import router as router_de_relatorios
from app.modules.vendas.router import router as router_de_vendas

api_router = APIRouter()
api_router.include_router(router_de_auth)
api_router.include_router(router_de_produtos)
api_router.include_router(router_de_locais)
api_router.include_router(router_de_dias_de_venda)
api_router.include_router(router_de_vendas)
api_router.include_router(router_de_relatorios)
api_router.include_router(router_de_historico)
api_router.include_router(router_de_midia)
api_router.include_router(router_de_ia)
api_router.include_router(router_de_custos)
