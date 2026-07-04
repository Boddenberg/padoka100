# Guia rapido da API

Base local:

```text
http://localhost:8000/api/v1
```

## 1. Criar produto visual

```bash
curl -X POST http://localhost:8000/api/v1/products \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Pao de calabresa",
    "description": "Pao recheado com calabresa",
    "visual_description": "Recheio alaranjado, formato comprido",
    "button_color": "#D97706",
    "sale_price": 10.00,
    "cost_price": 4.00,
    "effective_from": "2026-07-04"
  }'
```

## 2. Enviar foto do produto

```bash
curl -X POST http://localhost:8000/api/v1/products/PRODUCT_ID/media \
  -F "file=@calabresa.jpg" \
  -F "description=Foto do pao de calabresa" \
  -F "alt_text=Pao de calabresa em cima da mesa" \
  -F "set_as_main=true"
```

## 3. Mudar preco sem afetar passado

```bash
curl -X POST http://localhost:8000/api/v1/products/PRODUCT_ID/prices \
  -H "Content-Type: application/json" \
  -d '{
    "sale_price": 12.00,
    "cost_price": 4.50,
    "effective_from": "2026-07-10",
    "reason": "Aumento no custo dos ingredientes"
  }'
```

Vendas antes de `2026-07-10` continuam com o preco antigo porque `sale_items` salva `unit_sale_price_snapshot`.

## 4. Abrir dia com producao

```bash
curl -X POST http://localhost:8000/api/v1/sales-days \
  -H "Content-Type: application/json" \
  -d '{
    "business_date": "2026-07-04",
    "location_name": "Condominio Primavera",
    "production_items": [
      { "product_id": "PRODUCT_ID", "quantity_produced": 30 }
    ]
  }'
```

## 5. Registrar venda manual

```bash
curl -X POST http://localhost:8000/api/v1/sales \
  -H "Content-Type: application/json" \
  -d '{
    "sales_day_id": "SALES_DAY_ID",
    "input_type": "manual",
    "items": [
      { "product_id": "PRODUCT_ID", "quantity": 5 }
    ]
  }'
```

## 6. Interpretar venda por texto

```bash
curl -X POST http://localhost:8000/api/v1/ai/interpret-sale-command \
  -H "Content-Type: application/json" \
  -d '{
    "sales_day_id": "SALES_DAY_ID",
    "text": "vendi cinco paes de calabresa agora"
  }'
```

A resposta traz `confirmation_payload`. O front deve mostrar a confirmacao para o usuario.

## 7. Confirmar venda interpretada

```bash
curl -X POST http://localhost:8000/api/v1/ai/interactions/AI_INTERACTION_ID/confirm-sale
```

## 8. Enviar audio

```bash
curl -X POST http://localhost:8000/api/v1/ai/transcribe-sale-audio \
  -F "file=@venda.webm" \
  -F "sales_day_id=SALES_DAY_ID" \
  -F "interpret=true"
```

O audio e salvo no Supabase Storage e associado a `ai_interactions` quando `interpret=true`.

## 9. Ver resumo do dia

```bash
curl http://localhost:8000/api/v1/reports/days/SALES_DAY_ID/summary
```

O resumo retorna:

- produzido
- vendido
- sobra
- faturamento bruto
- custo estimado
- lucro estimado
- detalhes por produto

## 10. Ver historico

```bash
curl http://localhost:8000/api/v1/history/timeline?sales_day_id=SALES_DAY_ID
```

Eventos importantes entram em `timeline_events`: produto criado, preco alterado, dia aberto, producao adicionada, venda registrada, venda cancelada e midia enviada.

