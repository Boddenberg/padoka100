"""Nucleo puro do assistente de custeio.

Cada submodulo cobre uma etapa do assistente sem depender de FastAPI,
Supabase ou OpenAI:

- ``valores``: coercoes e normalizacoes de valores brutos vindos da IA/forms.
- ``ingredientes``: regras de nome, status e dados de compra de ingredientes.
- ``rascunho``: normalizacao e mesclagem do rascunho de custeio.
"""
