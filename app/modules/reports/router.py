from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.modules.auth.dependencias import exigir_capacidade, exigir_sessao_de_usuario
from app.modules.reports import servico
from app.modules.reports.esquemas import (
    AtualizarReportRequest,
    ReportAdminSaida,
    ReportSaida,
)

router = APIRouter(tags=["reports"])

SessaoUsuario = Annotated[dict, Depends(exigir_sessao_de_usuario)]
ReportsAdmin = Annotated[dict, Depends(exigir_capacidade("admin.gerenciar"))]


@router.post("/reports", response_model=ReportSaida, status_code=201)
async def criar_report(
    sessao: SessaoUsuario,
    tipo: Annotated[str | None, Form()] = None,
    mensagem: Annotated[str | None, Form()] = None,
    contexto: Annotated[str | None, Form()] = None,
    plataforma: Annotated[str | None, Form()] = None,
    app_versao: Annotated[str | None, Form()] = None,
    arquivos: Annotated[list[UploadFile] | None, File()] = None,
) -> dict:
    return await servico.criar_report(
        usuario=sessao["usuario"],
        tipo=tipo,
        mensagem=mensagem,
        contexto=contexto,
        plataforma=plataforma,
        app_versao=app_versao,
        arquivos=arquivos,
    )


@router.get("/admin/reports", response_model=list[ReportAdminSaida])
def listar_reports_admin(
    status: Annotated[str | None, Query(pattern="^(novo|lido|resolvido)$")] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 100,
    _: ReportsAdmin = None,
) -> list[dict]:
    return servico.listar_reports_admin(status=status, limite=limite)


@router.patch("/admin/reports/{report_id}", response_model=ReportAdminSaida)
def atualizar_report(
    report_id: UUID,
    requisicao: AtualizarReportRequest,
    _: ReportsAdmin = None,
) -> dict:
    return servico.atualizar_status_report(report_id, requisicao.status)
