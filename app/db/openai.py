"""Compatibilidade: o cliente OpenAI vive agora em app.infra.openai.client.

Mantido como reexport para nao quebrar imports existentes. Prefira importar de
``app.infra.openai.client`` em codigo novo.
"""

from app.infra.openai.client import get_openai_client

__all__ = ["get_openai_client"]
