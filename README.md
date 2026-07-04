# Padoka 100

Backend em Python/FastAPI para ajudar no controle visual de producao, vendas e historico da Padoka 100.

O foco do produto e ser simples para quem vende no dia a dia: cadastrar produtos com foto, abrir o dia de venda, registrar producao, registrar vendas por toque ou voz, fechar o dia e consultar historicos sem que mudancas futuras alterem numeros antigos.

## Stack

- Python 3.12+
- FastAPI
- Supabase Postgres
- Supabase Storage para fotos e audios
- OpenAI API para interpretar comandos por texto/audio

## Rodando localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
uvicorn app.main:app --reload
```

Depois de configurar as chaves no `.env`, aplique o SQL em `supabase/migrations/001_initial_schema.sql` no projeto Supabase.

A documentacao interativa fica em:

- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

## Endpoints principais

- `GET /health`
- `GET /api/v1/produtos`
- `POST /api/v1/produtos`
- `POST /api/v1/produtos/{produto_id}/precos`
- `POST /api/v1/produtos/{produto_id}/midia`
- `GET /api/v1/locais`
- `POST /api/v1/locais`
- `POST /api/v1/dias-de-venda`
- `GET /api/v1/dias-de-venda/atual`
- `POST /api/v1/dias-de-venda/{dia_de_venda_id}/itens-producao`
- `POST /api/v1/vendas`
- `POST /api/v1/vendas/{venda_id}/cancelar`
- `GET /api/v1/relatorios/dias/{dia_de_venda_id}/resumo`
- `GET /api/v1/relatorios/periodo`
- `GET /api/v1/historico/linha-do-tempo`
- `POST /api/v1/midia/{tipo_entidade}/{entidade_id}`
- `POST /api/v1/ia/interpretar-comando-de-venda`
- `POST /api/v1/ia/transcrever-audio-de-venda`
- `POST /api/v1/ia/interacoes/{interacao_ia_id}/confirmar-venda`

## Regra mais importante

Preco e historico nao podem ser reescritos.

Quando o preco de um produto muda, o backend cria uma nova versao de preco. Vendas e producoes salvam snapshots do nome, imagem e preco daquele dia. Assim, se o pao de calabresa custava R$ 8,00 na segunda e mudou para R$ 10,00 na quinta, a segunda continua mostrando R$ 8,00 para sempre.

Veja exemplos de uso em `docs/API_USAGE.md`.
