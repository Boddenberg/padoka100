# Seed de vendas fake

O endpoint `POST /api/v1/admin/seed/vendas-fake` gera massa isolada para um
usuario, destinada a testes de agentes, historico e analytics.

## Exemplo recomendado

```bash
curl --request POST "$BASE_URL/api/v1/admin/seed/vendas-fake" \
  --header "Content-Type: application/json" \
  --header "X-API-Key: $API_KEY" \
  --data '{
    "usuario_id": "COLOQUE-O-UUID-DO-USUARIO",
    "data_inicio": "2026-06-01",
    "data_fim": "2026-06-30",
    "produtos_por_dia_min": 2,
    "produtos_por_dia_max": 6,
    "vendas_por_dia_min": 18,
    "vendas_por_dia_max": 55,
    "itens_por_venda_min": 1,
    "itens_por_venda_max": 3,
    "quantidade_producao_min": 30,
    "quantidade_producao_max": 180,
    "quantidade_item_venda_min": 1,
    "quantidade_item_venda_max": 8,
    "probabilidade_reaproveitar_sobra": 0.65,
    "percentual_reaproveitamento_min": 0.25,
    "percentual_reaproveitamento_max": 1.0,
    "taxa_cancelamento": 0.04,
    "tipos_entrada": ["manual", "audio", "ia"],
    "fechar_dias": true,
    "limpar_seed_anterior": true,
    "criar_produtos_fake_se_necessario": true,
    "somente_simular": false,
    "seed": 20260714,
    "nome_local": "Seed Analytics",
    "observacao_base": "massa para validacao dos agentes"
  }'
```

Informe somente um seletor de usuario:

- `usuario_id`: opcao mais segura e recomendada;
- `usuario_email`: busca exata sem diferenciar maiusculas e minusculas;
- `usuario_nome`: busca parcial; nomes ambiguos devolvem erro com os candidatos.

Sem seletor, o endpoint preserva o comportamento anterior e usa o usuario da
credencial administrativa.

## Comportamento do catalogo

1. Se `produto_ids` for informado, usa apenas esses produtos.
2. Caso contrario, usa todos os produtos ativos do usuario que tenham preco
   vigente em cada dia do periodo.
3. Se existir ao menos um produto elegivel, nenhum produto fake e criado.
4. O fallback `[Seed]` so e criado quando nao existe produto elegivel e
   `criar_produtos_fake_se_necessario=true`.

## Variedade gerada

O gerador alterna cinco cenarios antes de repeti-los: `normal`,
`alta_demanda`, `baixa_demanda`, `excesso_producao` e `esgotamento`. Ele tambem:

- cria vendas em todos os dias do intervalo, respeitando os limites enviados;
- varia horario e origem (`manual`, `audio` ou `ia`);
- cria vendas canceladas conforme `taxa_cancelamento`;
- deixa estoque sem vender;
- grava a sobra em `decisoes_sobra` no dia seguinte;
- reaproveita ou descarta parte dela conforme as probabilidades configuradas;
- grava datas historicas coerentes nos dias, vendas e eventos da linha do tempo.

## Simular antes de gravar

Use `"somente_simular": true` para validar volume, cenarios e totais sem escrever
no banco. Depois envie o mesmo payload com `somente_simular=false` e a mesma
`seed`. As contagens e decisoes aleatorias serao reproduzidas; somente UUIDs do
lote e dos registros mudam.

O periodo aceita no maximo 120 dias e nao pode conter datas futuras.

