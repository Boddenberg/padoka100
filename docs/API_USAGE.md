# Guia rapido da API

Base local:

```text
http://localhost:8000/api/v1
```

## 1. Criar produto visual

```bash
curl -X POST http://localhost:8000/api/v1/produtos \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "Pao de calabresa",
    "descricao": "Pao recheado com calabresa",
    "descricao_visual": "Recheio alaranjado, formato comprido",
    "cor_botao": "#D97706",
    "preco_venda": 10.00,
    "preco_custo": 4.00,
    "vigente_desde": "2026-07-04"
  }'
```

## 2. Enviar foto do produto

```bash
curl -X POST http://localhost:8000/api/v1/produtos/PRODUTO_ID/midia \
  -F "file=@calabresa.jpg" \
  -F "descricao=Foto do pao de calabresa" \
  -F "texto_alternativo=Pao de calabresa em cima da mesa" \
  -F "definir_como_principal=true"
```

## 3. Mudar preco sem afetar passado

```bash
curl -X POST http://localhost:8000/api/v1/produtos/PRODUTO_ID/precos \
  -H "Content-Type: application/json" \
  -d '{
    "preco_venda": 12.00,
    "preco_custo": 4.50,
    "vigente_desde": "2026-07-10",
    "motivo": "Aumento no custo dos ingredientes"
  }'
```

Vendas antes de `2026-07-10` continuam com o preco antigo porque `itens_venda` salva `preco_venda_unitario_no_momento`.

## 4. Abrir dia com producao

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda \
  -H "Content-Type: application/json" \
  -d '{
    "data_venda": "2026-07-04",
    "nome_local": "Condominio Primavera",
    "itens_producao": [
      { "produto_id": "PRODUTO_ID", "quantidade_produzida": 30 }
    ]
  }'
```

## 5. Registrar venda manual

```bash
curl -X POST http://localhost:8000/api/v1/vendas \
  -H "Content-Type: application/json" \
  -d '{
    "dia_de_venda_id": "DIA_DE_VENDA_ID",
    "tipo_entrada": "manual",
    "itens": [
      { "produto_id": "PRODUTO_ID", "quantidade": 5 }
    ]
  }'
```

## 6. Interpretar comando por texto

```bash
curl -X POST http://localhost:8000/api/v1/ia/interpretar-comando \
  -H "Content-Type: application/json" \
  -d '{
    "dia_de_venda_id": "DIA_DE_VENDA_ID",
    "texto": "producao de hoje foi 10 paes de calabresa e 10 paes de queijo"
  }'
```

A resposta traz `mensagem_confirmacao` e `dados_confirmacao`. O front deve mostrar a mensagem para o usuario e so chamar a confirmacao se ele aceitar.

Para comandos com varios produtos na mesma acao, como `fiz 15 paes de soja e 15 paes de queijo`, a resposta vem com todos os itens em uma unica confirmacao. Nao e necessario criar um botao por item para esse fluxo.

Comandos suportados pelo fluxo generico:

- registrar venda
- registrar producao
- abrir dia de venda
- fechar dia de venda
- cancelar venda inteira
- cancelar item de venda, cancelando a venda original e criando uma venda corrigida com os itens restantes

No cancelamento parcial, a API nao apaga itens: ela preserva historico cancelando a venda original e registrando uma venda corrigida depois da confirmacao.

## 7. Confirmar comando interpretado

```bash
curl -X POST http://localhost:8000/api/v1/ia/interacoes/INTERACAO_IA_ID/confirmar
```

Quando a confirmacao conseguir aplicar a operacao, a resposta vem com `sucesso: true` e `resultado.aplicado: true`. Se a operacao nao puder ser aplicada porque algum dado ficou invalido ou sumiu entre a interpretacao e a confirmacao, a API responde sem erro HTTP, com `sucesso: false`, `resultado.aplicado: false` e uma mensagem amigavel em `mensagem_assistente` e `resultado.mensagem`.

As rotas antigas de venda continuam disponiveis:

```bash
curl -X POST http://localhost:8000/api/v1/ia/interpretar-comando-de-venda
curl -X POST http://localhost:8000/api/v1/ia/interacoes/INTERACAO_IA_ID/confirmar-venda
```

## 8. Enviar audio

```bash
curl -X POST http://localhost:8000/api/v1/ia/transcrever-audio \
  -F "file=@venda.webm" \
  -F "dia_de_venda_id=DIA_DE_VENDA_ID" \
  -F "interpretar=true"
```

O audio e salvo no Supabase Storage e associado a `interacoes_ia` quando `interpretar=true`.

## 9. Ver resumo do dia

```bash
curl http://localhost:8000/api/v1/relatorios/dias/DIA_DE_VENDA_ID/resumo
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
curl http://localhost:8000/api/v1/historico/linha-do-tempo?dia_de_venda_id=DIA_DE_VENDA_ID
```

Eventos importantes entram em `eventos_linha_do_tempo`: produto criado, preco alterado, dia aberto, producao adicionada, venda registrada, venda cancelada e midia enviada.

