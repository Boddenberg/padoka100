# Custeio Assistido - contrato para o front

O front deve tratar o custeio premium como uma sessao guiada. Ele nao precisa
chamar diretamente as rotas manuais de insumos, receitas e custos adicionais no
fluxo principal. Essas rotas continuam existindo para telas avancadas.

Base:

```text
/api/v1/custos/assistente
```

## Fluxo recomendado

1. O usuario entra em um produto cadastrado.
2. O front abre a aba `Custos`.
3. Se ainda nao houver sessao, cria uma sessao atrelada ao produto.
4. O usuario envia texto, audio, imagem/print ou formulario.
5. O backend devolve sempre a sessao completa, com rascunho, perguntas,
   pendencias, avisos e custo simulado.
6. O front renderiza uma tela de revisao editavel.
7. O usuario corrige campos pelo `PATCH /rascunho`.
8. Quando `pode_confirmar` for `true`, o front libera o botao de confirmar.
9. Ao confirmar, o backend grava insumos, receita, custos adicionais e atualiza
   o custo vigente do produto, se solicitado.

## Criar sessao

```http
POST /api/v1/custos/assistente/sessoes
Content-Type: application/json
```

```json
{
  "produto_id": "PRODUTO_ID",
  "contexto": "Usuario quer calcular o custo do Pao Sovado"
}
```

O `produto_id` pode ser omitido se o fluxo comecar fora do produto, mas o front
deve vincular um produto antes de confirmar.

## Enviar texto

```http
POST /api/v1/custos/assistente/sessoes/SESSAO_ID/entradas/texto
Content-Type: application/json
```

```json
{
  "texto": "Usei 800g de farinha. O pacote de 5kg custou 22 reais. Rendeu 12 unidades. Embalagem 35 centavos por unidade.",
  "contexto": "Receita base",
  "permitir_fallback": true
}
```

## Enviar formulario

Use quando o usuario preencher campos estruturados na tela.

```http
POST /api/v1/custos/assistente/sessoes/SESSAO_ID/entradas/formulario
Content-Type: application/json
```

```json
{
  "dados": {
    "receita": {
      "nome": "Receita base",
      "rendimento": 12,
      "unidade_rendimento": "unidade",
      "status": "CONFIRMADO"
    },
    "ingredientes": [
      {
        "nome": "Farinha de trigo",
        "quantidade_comprada": 5,
        "unidade_compra": "kg",
        "preco_total": 22,
        "quantidade_usada": 800,
        "unidade_usada": "g",
        "status": "CONFIRMADO"
      }
    ],
    "custos_adicionais": [
      {
        "tipo": "embalagem",
        "nome": "Saquinho",
        "valor": 0.35,
        "aplicacao": "por_unidade",
        "status": "CONFIRMADO"
      }
    ]
  }
}
```

## Enviar audio ou imagem

```http
POST /api/v1/custos/assistente/sessoes/SESSAO_ID/entradas/arquivo
Content-Type: multipart/form-data
```

Campos:

- `file`: arquivo.
- `tipo`: `audio` ou `imagem`.
- `contexto`: opcional.
- `permitir_fallback`: opcional, usado para audio apos transcricao.

Audio exige `OPENAI_API_KEY` e `OPENAI_TRANSCRIPTION_MODEL`.
Imagem exige `OPENAI_API_KEY` e `OPENAI_TEXT_MODEL`.

## Buscar estado da sessao

```http
GET /api/v1/custos/assistente/sessoes/SESSAO_ID
```

Campos importantes para o front:

- `rascunho`: fonte editavel da tela.
- `perguntas`: perguntas guiadas que o front deve destacar.
- `pendencias`: bloqueios para confirmacao.
- `avisos`: itens opcionais que merecem atencao.
- `custo_simulado`: custo total, custo por unidade, margem e detalhes.
- `pode_confirmar`: habilita/desabilita confirmacao.
- `proxima_acao`: orienta a tela atual.
- `entradas`: historico de texto/audio/imagem/formulario enviados.

## Corrigir rascunho

```http
PATCH /api/v1/custos/assistente/sessoes/SESSAO_ID/rascunho
Content-Type: application/json
```

```json
{
  "modo": "mesclar",
  "observacao": "Usuario corrigiu rendimento e embalagem",
  "rascunho": {
    "receita": {
      "rendimento": 10
    },
    "custos_adicionais": [
      {
        "tipo": "embalagem",
        "nome": "Saquinho",
        "valor": 0.25,
        "aplicacao": "por_unidade",
        "status": "CONFIRMADO"
      }
    ]
  }
}
```

Use `modo: "substituir"` somente se o front quiser trocar o rascunho inteiro.

## Confirmar

```http
POST /api/v1/custos/assistente/sessoes/SESSAO_ID/confirmar
Content-Type: application/json
```

```json
{
  "permitir_pendencias": false,
  "atualizar_preco_custo_produto": true,
  "vigente_desde": "2026-07-08",
  "motivo_preco": "Custo calculado pelo assistente"
}
```

Ao confirmar, o backend:

- cria insumos quando houver dados de compra;
- cria a receita do produto;
- cria custos adicionais;
- calcula o custo final;
- atualiza o `preco_custo` vigente do produto quando habilitado;
- marca a sessao como `confirmado`.

## Descartar

```http
POST /api/v1/custos/assistente/sessoes/SESSAO_ID/descartar
```

## Comportamento esperado de tela

A tela deve ser orientada por `proxima_acao`:

- `vincular_produto`: mostrar seletor de produto.
- `enviar_dados_de_custo`: mostrar botoes de texto, audio, imagem e formulario.
- `resolver_pendencias`: destacar perguntas e campos obrigatorios.
- `revisar_e_confirmar`: mostrar resumo financeiro e liberar confirmacao.
- `mostrar_custo_confirmado`: mostrar ficha final do custo.
- `sessao_descartada`: mostrar estado encerrado.

O front deve tratar `rascunho` como documento editavel. Ele pode montar cards de
ingredientes, rendimento, embalagem, custos indiretos e resumo a partir desse
campo, mas deve sempre considerar `custo_simulado` como a fonte do calculo.
