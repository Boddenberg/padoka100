# Relatorio de Implementacao e Curls

Este arquivo resume as funcionalidades implementadas nas ultimas levas e mostra
exemplos de uso via `curl`.

Base local:

```bash
BASE_URL="http://localhost:8000/api/v1"
```

Em Windows PowerShell, use a URL literal nos comandos ou adapte as variaveis para
`$env:BASE_URL`.

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
- Rotas sensiveis protegidas por papel.

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

## 2. Migrations novas

Aplique as migrations em ordem no Supabase:

```text
supabase/migrations/001_initial_schema.sql
supabase/migrations/002_decisoes_sobra.sql
supabase/migrations/003_correcoes_dia_fechado.sql
supabase/migrations/004_auth_perfil.sql
supabase/migrations/005_custos.sql
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

Guarde `access_token` da resposta e use:

```bash
TOKEN="COLE_O_ACCESS_TOKEN_AQUI"
```

### Ver perfil

```bash
curl http://localhost:8000/api/v1/perfil/me \
  -H "Authorization: Bearer $TOKEN"
```

### Atualizar perfil

```bash
curl -X PATCH http://localhost:8000/api/v1/perfil/me \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "nome": "Dono da Padoka 100",
    "telefone": "11988887777",
    "foto_url": "https://exemplo.com/foto.jpg"
  }'
```

### Trocar senha

```bash
curl -X POST http://localhost:8000/api/v1/auth/trocar-senha \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "senha_atual": "senha-segura-123",
    "nova_senha": "nova-senha-segura-456"
  }'
```

### Logout

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer $TOKEN"
```

### Listar usuarios

Exige papel `dono`.

```bash
curl http://localhost:8000/api/v1/auth/usuarios \
  -H "Authorization: Bearer $TOKEN"
```

### Alterar papel de usuario

Exige papel `dono`.

```bash
curl -X PATCH http://localhost:8000/api/v1/auth/usuarios/USUARIO_ID/papel \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "papel": "administrador"
  }'
```

## 4. Produtos e catalogo

### Criar produto

Exige `administrador` ou `dono`.

```bash
curl -X POST http://localhost:8000/api/v1/produtos \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
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

Exige `administrador` ou `dono`.

```bash
curl -X POST http://localhost:8000/api/v1/produtos/PRODUTO_ID/precos \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "preco_venda": 12.00,
    "preco_custo": 4.50,
    "vigente_desde": "2026-07-10",
    "motivo": "Aumento no custo dos ingredientes"
  }'
```

## 5. Dia de venda e operacao diaria

Rotas de `dias-de-venda`, `vendas` e `ia` exigem ao menos papel `usuario`.

### Abrir dia com producao

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
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
  -H "Authorization: Bearer $TOKEN" \
  -d '{}'
```

### Registrar producao no dia

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/DIA_DE_VENDA_ID/itens-producao \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "produto_id": "PRODUTO_ID",
    "quantidade_produzida": 20
  }'
```

### Registrar venda

```bash
curl -X POST http://localhost:8000/api/v1/vendas \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
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
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "motivo": "Lancamento errado"
  }'
```

### Fechar dia

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/DIA_DE_VENDA_ID/fechar \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "observacoes": "Dia encerrado"
  }'
```

## 6. Relatorios e venda do dia

Rotas de relatorio exigem papel `dono`.

### Resumo do dia por id

```bash
curl http://localhost:8000/api/v1/relatorios/dias/DIA_DE_VENDA_ID/resumo \
  -H "Authorization: Bearer $TOKEN"
```

### Resumo do dia por data

```bash
curl http://localhost:8000/api/v1/relatorios/dias/por-data/2026-07-04/resumo \
  -H "Authorization: Bearer $TOKEN"
```

### Produtos que participaram da venda do dia

```bash
curl http://localhost:8000/api/v1/relatorios/dias/DIA_DE_VENDA_ID/produtos-venda \
  -H "Authorization: Bearer $TOKEN"
```

### Resumo de periodo

```bash
curl "http://localhost:8000/api/v1/relatorios/periodo?data_inicio=2026-07-01&data_fim=2026-07-08" \
  -H "Authorization: Bearer $TOKEN"
```

### Resumo de periodo filtrando produto

```bash
curl "http://localhost:8000/api/v1/relatorios/periodo?data_inicio=2026-07-01&data_fim=2026-07-08&produto_id=PRODUTO_ID" \
  -H "Authorization: Bearer $TOKEN"
```

## 7. Correcoes retroativas

Exige `administrador` ou `dono`.

### Corrigir item de venda em dia fechado

```bash
curl -X POST http://localhost:8000/api/v1/dias-de-venda/DIA_DE_VENDA_ID/correcoes \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
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
  -H "Authorization: Bearer $TOKEN" \
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
  -H "Authorization: Bearer $TOKEN" \
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
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "dia_de_venda_id": "DIA_DE_VENDA_ID",
    "texto": "vendi 2 paes de queijo"
  }'
```

### Confirmar comando

```bash
curl -X POST http://localhost:8000/api/v1/ia/interacoes/INTERACAO_IA_ID/confirmar \
  -H "Authorization: Bearer $TOKEN"
```

### Transcrever audio

```bash
curl -X POST http://localhost:8000/api/v1/ia/transcrever-audio \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@venda.webm" \
  -F "dia_de_venda_id=DIA_DE_VENDA_ID" \
  -F "interpretar=true"
```

## 10. Dados estruturados e analises com IA

Rotas de analise exigem papel `dono`.

### Dados estruturados por periodo

```bash
curl "http://localhost:8000/api/v1/ia/dados-estruturados/periodo?data_inicio=2026-07-01&data_fim=2026-07-08" \
  -H "Authorization: Bearer $TOKEN"
```

### Analise padrao

```bash
curl -X POST http://localhost:8000/api/v1/ia/analises/padrao \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
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
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "data_inicio": "2026-07-01",
    "data_fim": "2026-07-08",
    "pergunta": "O que mais sobrou e o que devo produzir menos?"
  }'
```

## 11. Custos, insumos e receitas

Rotas de custos exigem papel `dono`.

### Criar insumo

```bash
curl -X POST http://localhost:8000/api/v1/custos/insumos \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
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
curl http://localhost:8000/api/v1/custos/insumos \
  -H "Authorization: Bearer $TOKEN"
```

### Atualizar insumo

```bash
curl -X PATCH http://localhost:8000/api/v1/custos/insumos/INSUMO_ID \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "preco_total": 5.50,
    "status": "CONFIRMADO"
  }'
```

### Criar receita

```bash
curl -X POST http://localhost:8000/api/v1/custos/produtos/PRODUTO_ID/receitas \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
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
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "tipo": "indireto",
    "nome": "gas",
    "valor": 3.00,
    "status": "ESTIMADO"
  }'
```

### Calcular custo do produto

```bash
curl http://localhost:8000/api/v1/custos/produtos/PRODUTO_ID/calculo \
  -H "Authorization: Bearer $TOKEN"
```

Exemplo esperado para farinha de R$ 5,00 por 1 kg:

```text
800 g usados na receita = R$ 4,00 de custo estimado.
```

## 12. Limites conhecidos

- A API cria auth proprio com PBKDF2 e bearer token; ainda nao ha refresh token.
- Ainda nao ha tela/front para gerir usuarios e papeis.
- Analise com IA depende de `OPENAI_API_KEY` e `OPENAI_TEXT_MODEL`; sem isso,
  retorna resumo local simples.
- Foto de nota fiscal e extracao OCR ainda nao foram implementadas.
- Ainda falta suite automatizada de testes de integracao.
