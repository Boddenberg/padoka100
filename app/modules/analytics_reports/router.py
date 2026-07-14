from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.modules.analytics_reports import servico
from app.modules.analytics_reports.esquemas import (
    DisponibilidadeRelatorioSaida,
    ProcessamentoPendenteSaida,
    RelatorioAnalyticsSaida,
    RequisicaoGerarRelatorio,
)
from app.modules.analytics_reports.pdf import gerar_pdf
from app.modules.auth.dependencias import exigir_capacidade

router = APIRouter(prefix="/analytics/relatorios", tags=["analytics-relatorios"])

Analytics = Annotated[dict, Depends(exigir_capacidade("relatorios.avancados"))]
AnalyticsAdmin = Annotated[dict, Depends(exigir_capacidade("admin.gerenciar"))]


@router.get("/disponibilidade", response_model=DisponibilidadeRelatorioSaida)
def consultar_disponibilidade(usuario: Analytics) -> dict:
    return servico.disponibilidade(usuario)


@router.get("", response_model=list[RelatorioAnalyticsSaida])
def listar_relatorios(
    limite: Annotated[int, Query(ge=1, le=100)] = 30,
    usuario: Analytics = None,
) -> list[dict]:
    return servico.listar_relatorios(usuario_id=usuario["id"], limite=limite)


@router.post("", response_model=RelatorioAnalyticsSaida, status_code=202)
def solicitar_relatorio(
    requisicao: RequisicaoGerarRelatorio,
    usuario: Analytics,
) -> dict:
    return servico.solicitar_relatorio(
        usuario=usuario,
        data_inicio=requisicao.data_inicio,
        data_fim=requisicao.data_fim,
    )


@router.post("/processar-pendentes", response_model=ProcessamentoPendenteSaida)
def processar_pendentes(_: AnalyticsAdmin = None) -> dict:
    from app.modules.analytics_reports.worker import retomar_pendentes

    return retomar_pendentes()


@router.get(
    "/compartilhados/{relatorio_id}/padoka-analytics.pdf",
    response_class=Response,
)
def exportar_pdf_compartilhado(relatorio_id: UUID, token: UUID) -> Response:
    relatorio = servico.buscar_por_token(relatorio_id, token)
    arquivo = gerar_pdf(relatorio)
    return Response(
        content=arquivo,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="padoka-analytics-{str(relatorio_id)[:8]}.pdf"'
            ),
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get("/{relatorio_id}", response_model=RelatorioAnalyticsSaida)
def buscar_relatorio(relatorio_id: UUID, usuario: Analytics) -> dict:
    return servico.buscar_relatorio(relatorio_id, usuario_id=usuario["id"])
