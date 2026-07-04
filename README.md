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

## Endpoints principais

- `GET /health`
- `GET /api/v1/products`
- `POST /api/v1/products`
- `POST /api/v1/products/{product_id}/prices`
- `POST /api/v1/products/{product_id}/media`
- `POST /api/v1/sales-days`
- `GET /api/v1/sales-days/current`
- `POST /api/v1/sales-days/{sales_day_id}/production-items`
- `POST /api/v1/sales`
- `POST /api/v1/sales/{sale_id}/void`
- `GET /api/v1/reports/days/{sales_day_id}/summary`
- `POST /api/v1/ai/interpret-sale-command`
- `POST /api/v1/ai/transcribe-sale-audio`

## Regra mais importante

Preco e historico nao podem ser reescritos.

Quando o preco de um produto muda, o backend cria uma nova versao de preco. Vendas e producoes salvam snapshots do nome, imagem e preco daquele dia. Assim, se o pao de calabresa custava R$ 8,00 na segunda e mudou para R$ 10,00 na quinta, a segunda continua mostrando R$ 8,00 para sempre.
