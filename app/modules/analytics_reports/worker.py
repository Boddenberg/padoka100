"""Executor serial: desacopla a solicitacao HTTP do processamento pesado."""

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import UUID

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="padoka-analytics")
_agendados: set[str] = set()
_lock = Lock()


def agendar(relatorio_id: UUID | str) -> bool:
    chave = str(relatorio_id)
    with _lock:
        if chave in _agendados:
            return False
        _agendados.add(chave)
    _executor.submit(_executar, chave)
    return True


def _executar(relatorio_id: str) -> None:
    try:
        from app.modules.analytics_reports.servico import processar_relatorio

        processar_relatorio(relatorio_id)
    except Exception:  # noqa: BLE001 - a falha ja e persistida pelo servico
        logger.exception("Falha inesperada no worker do relatorio %s", relatorio_id)
    finally:
        with _lock:
            _agendados.discard(relatorio_id)


def retomar_pendentes() -> dict:
    from app.modules.analytics_reports.servico import recuperar_e_listar_pendentes

    pendentes, recuperados = recuperar_e_listar_pendentes()
    agendados = sum(1 for relatorio_id in pendentes if agendar(relatorio_id))
    return {"agendados": agendados, "recuperados": recuperados}
