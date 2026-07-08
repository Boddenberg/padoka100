# Guia rapido da API

Base local:

```text
http://localhost:8000/api/v1
```

## 1. Autenticacao e perfil

O primeiro usuario cadastrado vira `dono`. Os proximos entram como `usuario`.

```bash
curl -X POST http://localhost:8000/api/v1/auth/registrar \
  -H "Content-Type: application/json" \
  -d '{
    "email": "dono@padoka.local",
    "senha": "senha-segura-123",
    "nome": "Dono da Padoka",
    "telefone": "11999999999"
  }'
```

Login:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "dono@padoka.local",
    "senha": "senha-segura-123"
  }'
```

Bearer token nao e obrigatorio em nenhuma rota. O login ainda devolve
`access_token` por compatibilidade, mas o front nao precisa enviar
`Authorization`.

```bash
curl http://localhost:8000/api/v1/perfil/me
```

Todas as rotas funcionam sem Bearer token:

- produtos, catalogo e midia;
- dias de venda, vendas e correcoes;
- relatorios e historico;
- IA operacional: interpretar, confirmar e transcrever;
- perfil, logout, troca de senha e gestao de usuarios;
- dados estruturados, analises de IA e custos.

Atualizar perfil, incluindo troca de e-mail:

```bash
curl -X PATCH http://localhost:8000/api/v1/perfil/me \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "Dono da Padoka",
    "email": "novo-email@padoka.local",
    "telefone": "11988887777",
    "foto_url": "https://exemplo.com/foto.jpg"
  }'
```

O campo `email` e aceito no `PATCH /perfil/me`. A API normaliza para minusculo
e retorna `409` se o e-mail ja estiver em uso por outro usuario.

Enviar foto de perfil do aparelho e salvar a URL no usuario:

```bash
curl -X POST http://localhost:8000/api/v1/perfil/me/foto \
  -F "file=@perfil.jpg"
```

O retorno e `UsuarioSaida` com `foto_url` atualizado:

```json
{
  "id": "USUARIO_ID",
  "email": "novo-email@padoka.local",
  "nome": "Dono da Padoka",
  "foto_url": "https://.../usuario/USUARIO_ID/arquivo.jpg",
  "data_nascimento": null,
  "telefone": "11988887777",
  "papel": "dono",
  "situacao": "ativo",
  "criado_em": "2026-07-08T10:00:00Z",
  "atualizado_em": "2026-07-08T10:05:00Z"
}
```

Trocar senha e sair:

```bash
curl -X POST http://localhost:8000/api/v1/auth/trocar-senha \
  -H "Content-Type: application/json" \
  -d '{
    "senha_atual": "senha-segura-123",
    "nova_senha": "nova-senha-segura-456"
  }'
curl -X POST http://localhost:8000/api/v1/auth/logout
```

Nao existe refresh token ainda. Quando receber `401`, o app deve derrubar a
sessao local e pedir login novamente.

Rotas de permissao para `dono`:

```bash
curl http://localhost:8000/api/v1/auth/usuarios
curl -X PATCH http://localhost:8000/api/v1/auth/usuarios/USUARIO_ID/papel
```

## 2. Criar produto visual

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

## 3. Enviar foto do produto

```bash
curl -X POST http://localhost:8000/api/v1/produtos/PRODUTO_ID/midia \
  -F "file=@calabresa.jpg" \
  -F "descricao=Foto do pao de calabresa" \
  -F "texto_alternativo=Pao de calabresa em cima da mesa" \
  -F "definir_como_principal=true"
```

## 4. Mudar preco sem afetar passado

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

## 5. Abrir dia com producao

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

## 5.1. Iniciar hoje com virada automatica

Use este endpoint na abertura do app ou no primeiro acesso do dia. Ele e idempotente:
se o dia de hoje ja estiver aberto, apenas devolve o dia atual.

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/iniciar-hoje \
  -H "Content-Type: application/json" \
  -d '{}'
```

Se existir um dia anterior aberto com sobra, a API nao fecha nem abre tudo sozinha.
Ela devolve `acao: "decidir_sobras"` para o front pedir a decisao do usuario:

```json
{
  "acao": "decidir_sobras",
  "mensagem": "Existe sobra do dia anterior. Escolha o que usar hoje antes de iniciar.",
  "data_venda": "2026-07-07",
  "sobras_pendentes": [
    {
      "produto_id": "PRODUTO_ID",
      "nome_produto": "Pao de calabresa",
      "quantidade_sobra": 12,
      "quantidade_sugerida_para_usar": 12
    }
  ]
}
```

Depois da escolha, chame o mesmo endpoint informando uma decisao para cada sobra.
Se `quantidade_nao_usada_hoje` for omitida, a API calcula o restante automaticamente.

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/iniciar-hoje \
  -H "Content-Type: application/json" \
  -d '{
    "decisoes_sobra": [
      {
        "produto_id": "PRODUTO_ID",
        "quantidade_usada_hoje": 8
      }
    ],
    "itens_producao": [
      { "produto_id": "PRODUTO_ID", "quantidade_produzida": 30 }
    ]
  }'
```

Nesse exemplo, o relatorio do novo dia mostra:

- produzido: 30
- sobra aproveitada: 8
- disponivel: 38

## 6. Registrar venda manual

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

## 7. Interpretar comando por texto

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

## 8. Confirmar comando interpretado

```bash
curl -X POST http://localhost:8000/api/v1/ia/interacoes/INTERACAO_IA_ID/confirmar
```

Quando a confirmacao conseguir aplicar a operacao, a resposta vem com `sucesso: true` e `resultado.aplicado: true`. Se a operacao nao puder ser aplicada porque algum dado ficou invalido ou sumiu entre a interpretacao e a confirmacao, a API responde sem erro HTTP, com `sucesso: false`, `resultado.aplicado: false` e uma mensagem amigavel em `mensagem_assistente` e `resultado.mensagem`.

As rotas antigas de venda continuam disponiveis:

```bash
curl -X POST http://localhost:8000/api/v1/ia/interpretar-comando-de-venda
curl -X POST http://localhost:8000/api/v1/ia/interacoes/INTERACAO_IA_ID/confirmar-venda
```

## 9. Enviar audio

```bash
curl -X POST http://localhost:8000/api/v1/ia/transcrever-audio \
  -F "file=@venda.webm" \
  -F "dia_de_venda_id=DIA_DE_VENDA_ID" \
  -F "interpretar=true"
```

O audio e salvo no Supabase Storage e associado a `interacoes_ia` quando `interpretar=true`.

## 10. Ver resumo do dia

```bash
curl http://localhost:8000/api/v1/relatorios/dias/DIA_DE_VENDA_ID/resumo
```

O resumo retorna:

- produzido
- sobra aproveitada
- disponivel
- vendido
- sobra
- faturamento bruto
- custo estimado
- lucro estimado
- detalhes por produto
- produtos produzidos
- produtos vendidos
- produtos sobrando
- produtos esgotados
- historico estruturado do dia
- correcoes retroativas do dia

Exemplo com os nomes exatos dos campos:

```json
{
  "dia_de_venda_id": "DIA_DE_VENDA_ID",
  "data_venda": "2026-07-04",
  "data": "2026-07-04",
  "nome_local": "Condominio Primavera",
  "situacao": "fechado",
  "status": "FECHADO",
  "total_produzido": 30,
  "total_sobra_aproveitada": 8,
  "total_disponivel": 38,
  "total_vendido": 25,
  "itens_vendidos": 25,
  "total_sobra": 13,
  "faturamento_bruto": "250.00",
  "faturamento_total": "250.00",
  "custo_estimado": "100.00",
  "lucro_estimado": "150.00",
  "produtos": [
    {
      "produto_id": "PRODUTO_ID",
      "nome_produto": "Pao de calabresa",
      "url_imagem_produto": "https://exemplo.com/calabresa.jpg",
      "participou_da_venda": true,
      "esgotado": false,
      "quantidade_produzida": 30,
      "quantidade_sobra_aproveitada": 8,
      "quantidade_disponivel": 38,
      "quantidade_vendida": 25,
      "quantidade_sobra": 13,
      "faturamento_bruto": "250.00",
      "custo_estimado": "100.00",
      "lucro_estimado": "150.00"
    }
  ],
  "produtos_produzidos": [],
  "produtos_vendidos": [],
  "produtos_sobrando": [],
  "produtos_esgotados": [],
  "historico": [],
  "correcoes": []
}
```

Tambem e possivel buscar por data:

```bash
curl http://localhost:8000/api/v1/relatorios/dias/por-data/2026-07-04/resumo
```

Para a aba de venda, use a lista filtrada de produtos que participaram do dia.
Produtos do catalogo que nao entraram no dia nao aparecem.
Produtos que entraram e esgotaram continuam aparecendo com `esgotado: true`.

```bash
curl http://localhost:8000/api/v1/relatorios/dias/DIA_DE_VENDA_ID/produtos-venda
```

O resumo de periodo bloqueia datas futuras e aceita filtro opcional por produto:

```bash
curl "http://localhost:8000/api/v1/relatorios/periodo?data_inicio=2026-07-01&data_fim=2026-07-08&produto_id=PRODUTO_ID"
```

## 11. Corrigir dia fechado

Dia fechado nao e reaberto sem controle. Use correcao retroativa para preservar
o antes/depois em `correcoes_dia_fechado` e registrar evento `CORRECAO_DIA_FECHADO`.

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/DIA_DE_VENDA_ID/correcoes \
  -H "Content-Type: application/json" \
  -d '{
    "usuario_id": "user-123",
    "motivo": "Venda lancada com quantidade errada",
    "itens_venda": [
      { "item_venda_id": "ITEM_VENDA_ID", "quantidade": 5 }
    ]
  }'
```

Campos aceitos na correcao:

- `producoes`: ajusta ou adiciona producao no dia fechado.
- `itens_venda`: corrige quantidade de um item de venda existente.
- `vendas_adicionadas`: adiciona venda retroativa ao dia fechado.
- `vendas_canceladas`: cancela venda existente do dia fechado.

## 12. Dados estruturados e analises com IA

Dados estruturados por periodo:

```bash
curl "http://localhost:8000/api/v1/ia/dados-estruturados/periodo?data_inicio=2026-07-01&data_fim=2026-07-08"
```

Analise padrao:

```bash
curl -X POST http://localhost:8000/api/v1/ia/analises/padrao \
  -H "Content-Type: application/json" \
  -d '{
    "data_inicio": "2026-07-01",
    "data_fim": "2026-07-08"
  }'
```

Analise especifica:

```bash
curl -X POST http://localhost:8000/api/v1/ia/analises/especifica \
  -H "Content-Type: application/json" \
  -d '{
    "data_inicio": "2026-07-01",
    "data_fim": "2026-07-08",
    "pergunta": "O que mais sobrou e o que devo produzir menos?"
  }'
```

`/analises/padrao` e `/analises/especifica` retornam o mesmo formato. O campo
`analise` continua existindo para compatibilidade com texto corrido, mas o app
pode renderizar preferencialmente as secoes estruturadas:

```json
{
  "periodo": {
    "inicio": "2026-07-01",
    "fim": "2026-07-08"
  },
  "tipo": "padrao",
  "modelo_usado": "analise-local",
  "dados_estruturados": {},
  "analise": "Periodo de 2026-07-01 a 2026-07-08...",
  "resumo": "Periodo de 2026-07-01 a 2026-07-08: faturamento total de R$ 650.00, 25 unidades vendidas e 13 unidades sobrando.",
  "principais_achados": [
    "Total produzido: 30 unidades.",
    "Total vendido: 25 unidades.",
    "Total sobrando: 13 unidades."
  ],
  "mais_venderam": [
    {
      "produto_id": "PRODUTO_ID",
      "produto": "Pao de calabresa",
      "quantidade_vendida": 25,
      "faturamento": "250.00"
    }
  ],
  "mais_sobraram": [
    {
      "produto_id": "PRODUTO_ID",
      "produto": "Pao de calabresa",
      "quantidade_sobra": 13
    }
  ],
  "sugestoes": [
    "Revisar a producao de Pao de calabresa, que concentrou a maior sobra."
  ],
  "pontos_atencao": [
    "Ha correcoes retroativas no periodo analisado."
  ]
}
```

Se `OPENAI_API_KEY` e `OPENAI_TEXT_MODEL` nao estiverem configurados, a API
preenche esses mesmos campos com uma analise local simples sem inventar dados.

## 13. Custos, insumos e receitas

Criar insumo:

```bash
curl -X POST http://localhost:8000/api/v1/custos/insumos \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "Farinha de trigo",
    "quantidade_comprada": 1,
    "unidade_compra": "kg",
    "preco_total": 5.00,
    "status": "CONFIRMADO"
  }'
```

Criar receita:

```bash
curl -X POST http://localhost:8000/api/v1/custos/produtos/PRODUTO_ID/receitas \
  -H "Content-Type: application/json" \
  -d '{
    "rendimento": 10,
    "ingredientes": [
      {
        "insumo_id": "INSUMO_ID",
        "nome": "Farinha de trigo",
        "quantidade_usada": 800,
        "unidade": "g",
        "status": "CONFIRMADO"
      }
    ]
  }'
```

Adicionar custo extra:

```bash
curl -X POST http://localhost:8000/api/v1/custos/produtos/PRODUTO_ID/custos-adicionais \
  -H "Content-Type: application/json" \
  -d '{
    "tipo": "indireto",
    "nome": "gas",
    "valor": 3.00,
    "status": "ESTIMADO"
  }'
```

Calcular custo:

```bash
curl http://localhost:8000/api/v1/custos/produtos/PRODUTO_ID/calculo
```

## 14. Custeio assistido

O fluxo premium de custo deve usar as rotas de sessao do assistente. O front
cria uma sessao, envia texto/audio/imagem/formulario, renderiza o rascunho
devolvido e confirma somente quando `pode_confirmar` estiver `true`.

Criar sessao atrelada ao produto:

```bash
curl -X POST http://localhost:8000/api/v1/custos/assistente/sessoes \
  -H "Content-Type: application/json" \
  -d '{
    "produto_id": "PRODUTO_ID"
  }'
```

Enviar texto:

```bash
curl -X POST http://localhost:8000/api/v1/custos/assistente/sessoes/SESSAO_ID/entradas/texto \
  -H "Content-Type: application/json" \
  -d '{
    "finalidade": "completo",
    "texto": "Usei 800g de farinha. O pacote de 5kg custou 22 reais. Rendeu 12 unidades. Embalagem 35 centavos por unidade."
  }'
```

Enviar arquivo de audio ou imagem:

```bash
curl -X POST http://localhost:8000/api/v1/custos/assistente/sessoes/SESSAO_ID/entradas/arquivo \
  -F "tipo=imagem" \
  -F "finalidade=receita" \
  -F "file=@nota-ou-print.jpg"
```

Use `finalidade=receita` para foto/print de receita e `finalidade=compras`
para nota/cupom/precos de mercado. Assim o backend nao copia quantidade usada
na receita para quantidade comprada. Na etapa de receita, as perguntas ficam
limitadas a receita/rendimento/medidas; dados de compra e preco aparecem depois,
agrupados em uma unica pergunta que pode ser respondida por texto ou foto da
notinha.

Corrigir rascunho:

```bash
curl -X PATCH http://localhost:8000/api/v1/custos/assistente/sessoes/SESSAO_ID/rascunho \
  -H "Content-Type: application/json" \
  -d '{
    "modo": "mesclar",
    "rascunho": {
      "receita": {
        "rendimento": 10
      }
    }
  }'
```

Confirmar e atrelar ao produto:

```bash
curl -X POST http://localhost:8000/api/v1/custos/assistente/sessoes/SESSAO_ID/confirmar \
  -H "Content-Type: application/json" \
  -d '{
    "permitir_pendencias": false,
    "atualizar_preco_custo_produto": true,
    "vigente_desde": "2026-07-08",
    "motivo_preco": "Custo calculado pelo assistente"
  }'
```

Contrato detalhado para o front: `docs/CUSTEIO_ASSISTIDO_FRONT.md`.

## 15. Ver historico

```bash
curl http://localhost:8000/api/v1/historico/linha-do-tempo?dia_de_venda_id=DIA_DE_VENDA_ID
```

Eventos importantes entram em `eventos_linha_do_tempo` com `tipo` publico em caixa alta,
`dataHora` e `dados`, alem dos campos antigos mantidos por compatibilidade.

