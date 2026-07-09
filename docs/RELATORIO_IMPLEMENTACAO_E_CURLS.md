# Relatorio de Implementacao e Curls

Este arquivo resume as funcionalidades implementadas nas ultimas levas e mostra
exemplos de uso via `curl`.

Base local:

```bash
BASE_URL="http://localhost:8000/api/v1"
```

Em Windows PowerShell, use a URL literal nos comandos ou adapte as variaveis para
`$env:BASE_URL`.

## Regra atual de autenticacao

Nenhum endpoint exige Bearer token. O login ainda devolve `access_token` por
compatibilidade, mas o front nao precisa enviar `Authorization`.

## 1. O que foi implementado

### Catalogo, venda do dia e historico

- Separacao entre catalogo e venda do dia.
- Produto do catalogo que nao entrou no dia nao aparece na aba de venda.
- Produto que entrou no dia e esgotou continua aparecendo com `esgotado: true`.
- Historico estruturado com `tipo`, `dataHora` e `dados`.
- Eventos publicos como `DIA_VENDA_ABERTO`, `VENDA_REALIZADA`,
  `VENDA_CANCELADA`, `PRODUTO_ESGOTADO` e `CORRECAO_DIA_FECHADO`.
- Bloqueio de datas futuras em consultas sensiveis.
- Resumo completo do dia por id e por data.
- Correcoes retroativas de dias fechados com auditoria.

### Autenticacao, perfil e permissoes

- Cadastro de usuario.
- Login com e-mail e senha.
- Senha com hash PBKDF2-HMAC.
- Sessao com token bearer armazenado por hash.
- Logout com revogacao de sessao.
- Troca de senha.
- Perfil do usuario com foto, nome, data de nascimento, telefone e e-mail.
- Papeis: `usuario`, `administrador`, `dono`.
- Primeiro usuario cadastrado vira `dono`.
- Rotas novas de conta, analise e custos funcionando sem Bearer token.

### IA e dados estruturados

- Dados estruturados para IA por periodo.
- Analise padrao de periodo.
- Analise especifica por pergunta do usuario.
- Quando OpenAI nao esta configurada, a API retorna uma analise local simples
  sem inventar dados.
- Analises consideram faturamento, producao, vendas, sobras, esgotados,
  comparacao entre dias e correcoes retroativas disponiveis.

### Custos, insumos e receitas

- Cadastro/listagem/atualizacao de insumos.
- Calculo de custo por unidade base, como grama, ml ou unidade.
- Cadastro de receita por produto.
- Ingredientes com insumo, quantidade usada, unidade e status.
- Custos adicionais por produto: embalagem, transporte, indireto ou outro.
- Calculo de custo por produto com:
  - custo total da receita;
  - rendimento;
  - custo por unidade;
  - custos incluidos;
  - status consolidado;
  - pendencias.
- Status suportados: `CONFIRMADO`, `ESTIMADO`, `PENDENTE`,
  `PRECISA_REVISAR`.
- Assistente de custeio com sessao, rascunho revisavel, entrada por texto,
  formulario, audio e imagem/print, simulacao, perguntas pendentes e
  confirmacao final atrelada ao produto.

## 2. Migrations novas

Aplique as migrations em ordem no Supabase:

```text
supabase/migrations/001_initial_schema.sql
supabase/migrations/002_decisoes_sobra.sql
supabase/migrations/003_correcoes_dia_fechado.sql
supabase/migrations/004_auth_perfil.sql
supabase/migrations/005_custos.sql
supabase/migrations/006_midias_usuario.sql
supabase/migrations/007_custeio_assistido.sql
supabase/migrations/008_notificacoes_rag_seed.sql
supabase/migrations/009_custos_historico_compras.sql
supabase/migrations/010_origem_ia_versoes_preco.sql
```

## 3. Autenticacao e perfil

### Registrar o primeiro usuario

O primeiro usuario cadastrado vira `dono`.

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

### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "dono@padoka.local",
    "senha": "senha-segura-123"
  }'
```

O `access_token` da resposta e opcional e existe por compatibilidade:

```bash
TOKEN="COLE_O_ACCESS_TOKEN_AQUI"
```

### Ver perfil

```bash
curl http://localhost:8000/api/v1/perfil/me \
```

### Atualizar perfil

```bash
curl -X PATCH http://localhost:8000/api/v1/perfil/me \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "Dono da Padoka 100",
    "email": "novo-email@padoka.local",
    "telefone": "11988887777",
    "foto_url": "https://exemplo.com/foto.jpg"
  }'
```

`PATCH /perfil/me` aceita troca de e-mail. A API normaliza o e-mail e retorna
`409` se ele ja estiver em uso.

### Enviar foto de perfil

```bash
curl -X POST http://localhost:8000/api/v1/perfil/me/foto \
  -F "file=@perfil.jpg"
```

O retorno e `UsuarioSaida` com `foto_url` atualizado.

### Trocar senha

```bash
curl -X POST http://localhost:8000/api/v1/auth/trocar-senha \
  -H "Content-Type: application/json" \
  -d '{
    "senha_atual": "senha-segura-123",
    "nova_senha": "nova-senha-segura-456"
  }'
```

### Logout

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout
```

### Listar usuarios

```bash
curl http://localhost:8000/api/v1/auth/usuarios
```

### Alterar papel de usuario

```bash
curl -X PATCH http://localhost:8000/api/v1/auth/usuarios/USUARIO_ID/papel \
  -H "Content-Type: application/json" \
  -d '{
    "papel": "administrador"
  }'
```

## 4. Produtos e catalogo

### Criar produto

Endpoint antigo: nao exige Bearer token.

```bash
curl -X POST http://localhost:8000/api/v1/produtos \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "Pao de Queijo",
    "descricao": "Pao de queijo tradicional",
    "descricao_visual": "Bolinha dourada",
    "cor_botao": "#D97706",
    "preco_venda": 10.00,
    "preco_custo": 4.00,
    "vigente_desde": "2026-07-04"
  }'
```

### Listar produtos

```bash
curl http://localhost:8000/api/v1/produtos
```

### Alterar preco

Endpoint antigo: nao exige Bearer token.

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

## 5. Dia de venda e operacao diaria

Endpoints antigos de `dias-de-venda`, `vendas` e IA operacional nao exigem Bearer token.

### Abrir dia com producao

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda \
  -H "Content-Type: application/json" \
  -d '{
    "data_venda": "2026-07-04",
    "nome_local": "Condominio Primavera",
    "itens_producao": [
      {
        "produto_id": "PRODUTO_ID",
        "quantidade_produzida": 30
      }
    ]
  }'
```

### Iniciar hoje

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/iniciar-hoje \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Registrar producao no dia

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/DIA_DE_VENDA_ID/itens-producao \
  -H "Content-Type: application/json" \
  -d '{
    "produto_id": "PRODUTO_ID",
    "quantidade_produzida": 20
  }'
```

### Registrar venda

```bash
curl -X POST http://localhost:8000/api/v1/vendas \
  -H "Content-Type: application/json" \
  -d '{
    "dia_de_venda_id": "DIA_DE_VENDA_ID",
    "tipo_entrada": "manual",
    "itens": [
      {
        "produto_id": "PRODUTO_ID",
        "quantidade": 5
      }
    ]
  }'
```

### Cancelar venda

```bash
curl -X POST http://localhost:8000/api/v1/vendas/VENDA_ID/cancelar \
  -H "Content-Type: application/json" \
  -d '{
    "motivo": "Lancamento errado"
  }'
```

### Fechar dia

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/DIA_DE_VENDA_ID/fechar \
  -H "Content-Type: application/json" \
  -d '{
    "observacoes": "Dia encerrado"
  }'
```

## 6. Relatorios e venda do dia

Endpoints antigos de relatorio nao exigem Bearer token.

### Resumo do dia por id

```bash
curl http://localhost:8000/api/v1/relatorios/dias/DIA_DE_VENDA_ID/resumo
```

### Resumo do dia por data

```bash
curl http://localhost:8000/api/v1/relatorios/dias/por-data/2026-07-04/resumo
```

### Produtos que participaram da venda do dia

```bash
curl http://localhost:8000/api/v1/relatorios/dias/DIA_DE_VENDA_ID/produtos-venda
```

### Resumo de periodo

```bash
curl "http://localhost:8000/api/v1/relatorios/periodo?data_inicio=2026-07-01&data_fim=2026-07-08"
```

### Resumo de periodo filtrando produto

```bash
curl "http://localhost:8000/api/v1/relatorios/periodo?data_inicio=2026-07-01&data_fim=2026-07-08&produto_id=PRODUTO_ID"
```

### Exemplo de resposta do resumo do dia

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
      "quantidade_produzida": 30,
      "quantidade_sobra_aproveitada": 8,
      "quantidade_disponivel": 38,
      "quantidade_vendida": 25,
      "quantidade_sobra": 13,
      "esgotado": false
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

## 7. Correcoes retroativas

Endpoint antigo: nao exige Bearer token.

### Corrigir item de venda em dia fechado

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/DIA_DE_VENDA_ID/correcoes \
  -H "Content-Type: application/json" \
  -d '{
    "usuario_id": "USUARIO_ID",
    "motivo": "Venda lancada com quantidade errada",
    "itens_venda": [
      {
        "item_venda_id": "ITEM_VENDA_ID",
        "quantidade": 5
      }
    ]
  }'
```

### Adicionar venda retroativa em dia fechado

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/DIA_DE_VENDA_ID/correcoes \
  -H "Content-Type: application/json" \
  -d '{
    "usuario_id": "USUARIO_ID",
    "motivo": "Venda esquecida",
    "vendas_adicionadas": [
      {
        "observacoes": "Venda lancada depois do fechamento",
        "itens": [
          {
            "produto_id": "PRODUTO_ID",
            "quantidade": 2
          }
        ]
      }
    ]
  }'
```

### Ajustar producao em dia fechado

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/DIA_DE_VENDA_ID/correcoes \
  -H "Content-Type: application/json" \
  -d '{
    "usuario_id": "USUARIO_ID",
    "motivo": "Producao informada errada",
    "producoes": [
      {
        "produto_id": "PRODUTO_ID",
        "quantidade_produzida": 25
      }
    ]
  }'
```

## 8. Historico estruturado

```bash
curl http://localhost:8000/api/v1/historico/linha-do-tempo?dia_de_venda_id=DIA_DE_VENDA_ID
```

O retorno inclui campos antigos e tambem:

```json
{
  "tipo": "VENDA_REALIZADA",
  "dataHora": "2026-07-08T10:30:00Z",
  "dados": {}
}
```

## 9. IA operacional

### Interpretar comando

```bash
curl -X POST http://localhost:8000/api/v1/ia/interpretar-comando \
  -H "Content-Type: application/json" \
  -d '{
    "dia_de_venda_id": "DIA_DE_VENDA_ID",
    "texto": "vendi 2 paes de queijo"
  }'
```

### Confirmar comando

```bash
curl -X POST http://localhost:8000/api/v1/ia/interacoes/INTERACAO_IA_ID/confirmar
```

### Transcrever audio

```bash
curl -X POST http://localhost:8000/api/v1/ia/transcrever-audio \
  -F "file=@venda.webm" \
  -F "dia_de_venda_id=DIA_DE_VENDA_ID" \
  -F "interpretar=true"
```

## 10. Dados estruturados e analises com IA

Rotas de analise nao exigem Bearer token.

### Dados estruturados por periodo

```bash
curl "http://localhost:8000/api/v1/ia/dados-estruturados/periodo?data_inicio=2026-07-01&data_fim=2026-07-08"
```

### Analise padrao

```bash
curl -X POST http://localhost:8000/api/v1/ia/analises/padrao \
  -H "Content-Type: application/json" \
  -d '{
    "data_inicio": "2026-07-01",
    "data_fim": "2026-07-08",
    "contexto_usuario": "Quero entender a producao da semana"
  }'
```

### Analise especifica

```bash
curl -X POST http://localhost:8000/api/v1/ia/analises/especifica \
  -H "Content-Type: application/json" \
  -d '{
    "data_inicio": "2026-07-01",
    "data_fim": "2026-07-08",
    "pergunta": "O que mais sobrou e o que devo produzir menos?"
  }'
```

### Resposta padronizada da analise

`/analises/padrao` e `/analises/especifica` retornam as mesmas secoes. O campo
`analise` continua disponivel como texto corrido.

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

## 11. Custos, insumos e receitas

Rotas de custos nao exigem Bearer token.

### Criar insumo

```bash
curl -X POST http://localhost:8000/api/v1/custos/insumos \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "Farinha de trigo",
    "categoria": "ingrediente principal",
    "quantidade_comprada": 1,
    "unidade_compra": "kg",
    "preco_total": 5.00,
    "status": "CONFIRMADO"
  }'
```

### Listar insumos

```bash
curl http://localhost:8000/api/v1/custos/insumos
```

### Atualizar insumo

```bash
curl -X PATCH http://localhost:8000/api/v1/custos/insumos/INSUMO_ID \
  -H "Content-Type: application/json" \
  -d '{
    "preco_total": 5.50,
    "status": "CONFIRMADO"
  }'
```

### Criar receita

```bash
curl -X POST http://localhost:8000/api/v1/custos/produtos/PRODUTO_ID/receitas \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "Receita base de Pao Sovado",
    "rendimento": 10,
    "unidade_rendimento": "unidade",
    "status": "ESTIMADO",
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

### Adicionar custo extra

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

### Calcular custo do produto

```bash
curl http://localhost:8000/api/v1/custos/produtos/PRODUTO_ID/calculo
```

Exemplo esperado para farinha de R$ 5,00 por 1 kg:

```text
800 g usados na receita = R$ 4,00 de custo estimado.
```

## 12. Limites conhecidos

- A API cria auth proprio com PBKDF2 e bearer token; ainda nao ha refresh token.
- Ainda nao ha tela/front para gerir usuarios e papeis.
- Analise com IA depende de `OPENAI_API_KEY` e `OPENAI_TEXT_MODEL`; sem isso,
  retorna as mesmas secoes estruturadas com analise local simples.
- O assistente de custeio aceita imagem/print com leitura por OpenAI Vision,
  mas ainda nao ha integracao fiscal oficial por XML ou chave de acesso.
- Ainda falta suite automatizada de testes de integracao.
