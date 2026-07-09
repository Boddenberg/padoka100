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
  "finalidade": "completo",
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
  "finalidade": "receita",
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

Para formulario de compras/precos, use `finalidade: "compras"` e mande somente
os dados de compra do insumo:

```json
{
  "finalidade": "compras",
  "dados": {
    "ingredientes": [
      {
        "nome": "Farinha de trigo",
        "quantidade_comprada": 5,
        "unidade_compra": "kg",
        "preco_total": 22,
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
- `finalidade`: `auto`, `receita`, `compras` ou `completo`.
- `permitir_fallback`: opcional, usado para audio apos transcricao.

Audio exige `OPENAI_API_KEY` e `OPENAI_TRANSCRIPTION_MODEL`.
Imagem exige `OPENAI_API_KEY` e `OPENAI_TEXT_MODEL`.

Jornada recomendada:

- foto/print de receita: `finalidade=receita`;
- foto/print de nota fiscal, cupom ou mercado: `finalidade=compras`;
- entrada misturada de receita + precos: `finalidade=completo`;
- `auto` existe por compatibilidade, mas o front deve preferir finalidade
  explicita para evitar mistura de etapa.

Quando `finalidade=receita`, o backend nao preenche `quantidade_comprada`,
`unidade_compra` nem `preco_total`, mesmo que a receita diga `250 ml de leite`.
Nessa fase, `perguntas` tambem nao deve trazer preco: se faltar medida de
ingrediente, o backend agrupa em uma unica pergunta de receita.
Quando `finalidade=compras`, o backend nao sobrescreve rendimento nem
quantidade usada da receita; ele apenas atualiza dados de compra/preco.
Quando chegar em `coletando_precos`, o backend agrupa os ingredientes sem custo
em uma pergunta unica, aceitando resposta por texto ou foto/print da notinha.

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
- `fase`: etapa real da sessao para rotular a tela.
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

Em `coletando_ingredientes`, o front deve mostrar somente receita: ingredientes,
quantidades usadas, rendimento e preparo. Perguntas de preco aparecem apenas
quando a fase evolui para `coletando_precos`; nesse momento, prefira uma caixa
unica de resposta com opcoes de texto e upload da nota/cupom.

O front deve tratar `rascunho` como documento editavel. Ele pode montar cards de
ingredientes, rendimento, embalagem, custos indiretos e resumo a partir desse
campo, mas deve sempre considerar `custo_simulado` como a fonte do calculo.

Para mostrar o custo destrinchado por ingrediente, leia
`custo_simulado.ingredientes[]`. Campos importantes:

- `nome`: nome do ingrediente da receita.
- `quantidade_usada` e `unidade_usada`: valor original lido/informado.
- `quantidade_usada_calculo` e `unidade_usada_calculo`: valor efetivamente usado
  no calculo depois de conversoes/estimativas.
- `quantidade_comprada`, `unidade_compra` e `preco_total`: dados da nota/compra.
- `custo_unitario_base`: custo por unidade base calculada pelo backend.
- `custo_total_estimado`: custo daquele ingrediente na receita.
- `formula_calculo`: texto pronto com o resumo do calculo.
- `calculo_estimado`: `true` quando o backend assumiu alguma equivalencia, por
  exemplo `1 ou 2 ovos -> 2 ovos` ou `1 colher de sal -> 15 g`.
- `avisos_calculo`: avisos especificos do ingrediente para exibir junto ao item.

## Unidades e conversao

O backend converte unidades compativeis automaticamente. Exemplos:

- massa: `kg`, `g`, `quilo`, `grama`;
- volume: `l`, `ml`, `litro`, `copo`, `copo americano`, `xicara`,
  `colher de sopa`, `colher de cha`;
- unidade: `un`, `und`, `unidade`, `ovo`, `ovos`, `duzia`, `cartela`.

Medidas caseiras usam padrao aproximado:

- `copo` ou `copo americano`: 200 ml;
- `xicara`: 240 ml;
- `colher de sopa`: 15 ml;
- `colher de cha`: 5 ml.
- `prato cheio`: 350 g;
- `cartela de ovos`: 30 unidades.

Se o usuario informar o tamanho no texto ou formulario, por exemplo
`copo de 250ml`, `prato cheio (350 g)` ou `cartela de 12 ovos`, o backend usa
essa equivalencia em vez do padrao. Quando a simulacao usar medida caseira
aproximada, o campo `avisos` da sessao trara um alerta para o front pedir
confirmacao visual.

## Merge e insumos compartilhados

Ao receber novas entradas, o backend junta ingredientes por nome normalizado.
Exemplo: `queijo mussarela ralado`, `mussarela` e `mucarela` devem atualizar o
mesmo item do rascunho em vez de criar linhas duplicadas.

Na confirmacao, se um ingrediente tiver o mesmo nome de um insumo ja cadastrado,
o backend reutiliza esse insumo. Se a nova entrada trouxer preco, quantidade de
compra e unidade de compra, o backend atualiza o insumo existente com o preco
mais recente e usa o mesmo `insumo_id` na receita.

Fases possiveis:

- `vinculando_produto`;
- `coletando_ingredientes`;
- `coletando_precos`;
- `revisando`;
- `confirmada`;
- `descartada`.
