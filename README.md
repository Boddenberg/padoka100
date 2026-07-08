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

Depois de configurar as chaves no `.env`, aplique os SQLs de `supabase/migrations` em ordem no projeto Supabase.

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
- `POST /api/v1/dias-de-venda/iniciar-hoje`
- `GET /api/v1/dias-de-venda/atual`
- `POST /api/v1/dias-de-venda/{dia_de_venda_id}/itens-producao`
- `POST /api/v1/vendas`
- `POST /api/v1/vendas/{venda_id}/cancelar`
- `GET /api/v1/relatorios/dias/{dia_de_venda_id}/resumo`
- `GET /api/v1/relatorios/periodo`
- `GET /api/v1/historico/linha-do-tempo`
- `POST /api/v1/midia/{tipo_entidade}/{entidade_id}`
- `POST /api/v1/ia/interpretar-comando`
- `POST /api/v1/ia/transcrever-audio`
- `POST /api/v1/ia/interacoes/{interacao_ia_id}/confirmar`
- `POST /api/v1/ia/interpretar-comando-de-venda`
- `POST /api/v1/ia/transcrever-audio-de-venda`
- `POST /api/v1/ia/interacoes/{interacao_ia_id}/confirmar-venda`

## Regra mais importante

Preco e historico nao podem ser reescritos.

Quando o preco de um produto muda, o backend cria uma nova versao de preco. Vendas e producoes salvam snapshots do nome, imagem e preco daquele dia. Assim, se o pao de calabresa custava R$ 8,00 na segunda e mudou para R$ 10,00 na quinta, a segunda continua mostrando R$ 8,00 para sempre.

## Roadmap

### Ja feito

- Estrutura inicial em Python/FastAPI com `app.main:app`, CORS, healthcheck e configuracao por `.env`.
- Padrao de dominio em portugues para modulos, servicos, funcoes, schemas, payloads e rotas de negocio.
- Integracao preparada para Supabase com cliente lazy e erro claro quando as chaves ainda nao estao configuradas.
- Integracao preparada para OpenAI com cliente dedicado e modelos configuraveis por ambiente.
- Migration inicial do Supabase em `supabase/migrations/001_initial_schema.sql`.
- Tabelas principais em portugues: `produtos`, `versoes_preco_produto`, `locais`, `dias_de_venda`, `itens_producao`, `decisoes_sobra`, `vendas`, `itens_venda`, `midias`, `interacoes_ia` e `eventos_linha_do_tempo`.
- Cadastro, listagem, atualizacao e consulta de produtos.
- Produtos preparados para uso visual com descricao, descricao visual, cor de botao, ordem de exibicao e imagem principal.
- Historico de precos por versao, com vigencia por data e sem sobrescrever o passado.
- Cadastro e atualizacao de locais/condominios.
- Abertura, edicao, consulta e fechamento de dias de venda.
- Virada de dia com fechamento do dia anterior, abertura do dia atual e decisao explicita sobre sobras.
- Registro de producao do dia com snapshot de produto, imagem e preco vigente.
- Registro de vendas manuais com snapshots de nome, imagem, preco de venda e custo.
- Cancelamento de venda sem apagar historico.
- Relatorios por dia e por periodo com produzido, sobra aproveitada, disponivel, vendido, sobra, faturamento bruto, custo estimado e lucro estimado.
- Linha do tempo para eventos importantes: produto criado, preco alterado, dia aberto, producao adicionada, venda registrada, venda cancelada e midia enviada.
- Upload de midia para produtos, locais, dias de venda, vendas e interacoes de IA.
- Fluxo de IA para interpretar comandos por texto: venda, producao, abertura/fechamento de dia, cancelamento de venda e ajuste de item vendido.
- Fluxo de audio para transcrever fala, interpretar comando e salvar o audio associado.
- Confirmacao explicita antes de transformar qualquer interpretacao de IA em mudanca real no banco.
- Documentacao de exemplos em `docs/API_USAGE.md`.
- Plano tecnico em `docs/IMPLEMENTATION_PLAN.md`.

### Proximos passos recomendados

1. Configurar o projeto Supabase real e aplicar `supabase/migrations/001_initial_schema.sql`.
2. Preencher `.env` com `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY`, `OPENAI_TEXT_MODEL` e `OPENAI_TRANSCRIPTION_MODEL`.
3. Fazer um teste ponta a ponta com dados reais: criar produto, enviar foto, abrir dia, registrar producao, registrar venda, fechar dia e consultar resumo.
4. Revisar permissoes/RLS do Supabase antes de expor a API para um app real.
5. Adicionar autenticacao simples para proteger o uso da API.
6. Melhorar o fluxo de midia com validacao de tipo/tamanho de arquivo e tratamento de conflito quando arquivo ja existe no Storage.
7. Criar endpoints de despesas do dia para calcular lucro com custos extras, como transporte, embalagem e ingredientes comprados em cima da hora.
8. Adicionar formas de pagamento, como dinheiro, Pix, cartao e fiado, se fizer sentido para a rotina.
9. Criar consultas mais praticas para o app, como produtos mais vendidos, sobras recorrentes e melhores dias/locais.
10. Melhorar a interpretacao por IA com exemplos reais de fala do seu pai e mensagens de confirmacao mais naturais.
11. Criar testes de integracao para os fluxos principais depois que o banco estiver configurado.
12. Construir o front primeiro como web responsivo ou PWA, com botoes grandes, fotos dos produtos e fluxo de venda em poucos toques.
13. Depois avaliar empacotar como app Android, usando a mesma API.
14. Fazer uma tela de "modo venda" extremamente simples: botoes por produto, botao de audio, resumo do dia e desfazer/cancelar ultima venda.
15. Fazer uma tela de historico visual por dia, deixando claro qual preco foi usado em cada venda.

Veja exemplos de uso em `docs/API_USAGE.md`.

## Deploy

Para publicar a API, veja `docs/DEPLOYMENT.md`.


fiz até o 12

dps ponho de novo aq - >


## 13. Autenticação

A autenticação precisa entrar como funcionalidade real do projeto.

O back-end deve suportar:

- criação de usuário;
- login com usuário/e-mail e senha;
- armazenamento seguro de senha;
- autenticação por token ou sessão;
- proteção de rotas;
- identificação do usuário autenticado;
- logout, se aplicável ao modelo escolhido;
- troca de senha;
- alteração de e-mail ou usuário;
- sessão expirada;
- validação de permissões.

A troca de senha deve ser segura e bem estruturada.

---

## 14. Perfil do usuário

O perfil deve armazenar dados como:

- foto;
- nome;
- data de nascimento;
- telefone;
- e-mail.

Esses dados podem futuramente ajudar a IA a personalizar respostas ou entender melhor o contexto da conta.

---

## 15. Permissões futuras

Como haverá autenticação, a arquitetura deve permitir permissões diferentes no futuro.

Possibilidades:

```txt
Usuário comum:
pode vender e consultar dados básicos.

Administrador:
pode corrigir dias fechados e alterar cadastro de produtos.

Dono:
pode consultar relatórios, IA e dados financeiros.
```

Não precisa implementar tudo imediatamente, mas a arquitetura deve permitir evolução.

---

## 16. Dados estruturados para Inteligência Artificial

O back-end precisa organizar os dados para que a IA consiga analisar vendas sem receber dados crus e bagunçados.

A ideia é montar estruturas por:

- dia;
- semana;
- mês;
- período personalizado;
- produto;
- categoria, se existir futuramente.

Exemplo de resumo diário:

```json
{
  "data": "2026-07-08",
  "faturamentoTotal": 650,
  "quantidadeTotalProduzida": 46,
  "quantidadeTotalVendida": 25,
  "quantidadeTotalSobrando": 21,
  "produtos": [
    {
      "produto": "Pão de Queijo",
      "quantidadeProduzida": 20,
      "quantidadeVendida": 20,
      "quantidadeSobrando": 0,
      "faturamento": 300
    }
  ]
}
```

Exemplo de resumo por período:

```json
{
  "periodo": {
    "inicio": "2026-07-01",
    "fim": "2026-07-08"
  },
  "faturamentoTotal": 3200,
  "quantidadeTotalVendida": 140,
  "produtos": [
    {
      "produto": "Pão de Queijo",
      "totalProduzido": 100,
      "totalVendido": 90,
      "totalSobrando": 10,
      "faturamento": 1350
    }
  ]
}
```

---

## 17. Análise padrão com IA

O back-end precisa permitir uma análise padrão baseada no período selecionado no front-end.

Exemplo:

```txt
Usuário seleciona julho.
Clica em Solicitar análise.
O back-end monta os dados de julho.
A IA gera uma análise geral.
```

A análise padrão deve considerar:

- faturamento;
- produtos vendidos;
- produtos produzidos;
- sobras;
- produtos esgotados;
- comparação entre dias;
- histórico de vendas;
- correções retroativas, se relevantes.

---

## 18. Análise específica com IA

Além da análise padrão, o back-end precisa aceitar pedidos específicos do usuário.

Exemplos:

```txt
Analise somente abril.
Ignore os pudins.
Veja só o pão de calabresa.
Compare pão de queijo com pão sovado.
Me diga o que mais sobrou.
Me diga o que eu deveria produzir menos.
```

O back-end precisa receber:

- período selecionado;
- contexto opcional do usuário;
- dados estruturados do período;
- possíveis filtros solicitados pelo usuário.

A IA deve conseguir responder com base nesses dados, sem inventar informações.

---

## 19. Cálculo de custo dos produtos

Esta será uma das funcionalidades mais complexas do projeto.

O objetivo é ajudar a identificar o custo real de cada produto.

O dono da padaria pode não saber exatamente o custo do produto. Então o sistema precisa permitir que ele informe dados aos poucos.

---

### 19.1 Informações necessárias para custo

O sistema precisa conseguir guardar:

- insumos comprados;
- preço dos insumos;
- quantidade comprada;
- unidade de medida;
- receita do produto;
- quantidade usada na receita;
- rendimento da receita;
- custos indiretos;
- embalagem;
- transporte;
- status de confirmação das informações.

---

### 19.2 Insumos

Exemplo:

```json
{
  "nome": "Farinha de trigo",
  "quantidadeComprada": 1,
  "unidadeCompra": "kg",
  "precoTotal": 5.00,
  "custoPorUnidade": 5.00
}
```

---

### 19.3 Receita

Exemplo:

```json
{
  "produto": "Pão Sovado",
  "rendimento": 10,
  "ingredientes": [
    {
      "nome": "Farinha de trigo",
      "quantidadeUsada": 800,
      "unidade": "g"
    },
    {
      "nome": "Leite",
      "quantidadeUsada": 300,
      "unidade": "ml"
    }
  ]
}
```

---

### 19.4 Custo calculado

Exemplo:

```json
{
  "produto": "Pão Sovado",
  "custoTotalReceita": 28.50,
  "rendimento": 10,
  "custoPorUnidade": 2.85,
  "custosIncluidos": {
    "ingredientes": true,
    "embalagem": true,
    "gas": true,
    "energia": false,
    "transporte": false
  },
  "status": "CONFIRMADO"
}
```

---

### 19.5 Custos que precisam poder entrar no cálculo

Ingredientes principais:

- farinha;
- leite;
- ovos;
- queijo;
- calabresa;
- presunto;
- frango;
- açúcar;
- manteiga;
- óleo;
- fermento.

Ingredientes pequenos:

- sal;
- temperos;
- orégano;
- alho;
- cebola;
- essência.

Custos indiretos:

- gás;
- energia elétrica;
- água;
- tempo de forno;
- geladeira/freezer, se fizer sentido;
- desgaste de equipamento, futuramente.

Embalagem:

- saquinho;
- bandeja;
- etiqueta;
- caixa;
- papel;
- plástico filme.

Transporte:

- gasolina;
- estacionamento;
- frete;
- taxa de entrega.

---

### 19.6 Status das informações

Como algumas informações podem estar incompletas ou estimadas, o sistema precisa marcar o status.

Exemplos:

```txt
CONFIRMADO
ESTIMADO
PENDENTE
PRECISA_REVISAR
```

Exemplo:

```json
{
  "nome": "Gás",
  "valor": 3.00,
  "status": "ESTIMADO"
}
```

A IA precisa saber se um dado é confirmado ou estimado.

---

### 19.7 IA para custo

A IA deve ajudar a montar o custo, mas não pode inventar dados.

Regra principal:

```txt
Se não souber, pergunta.
Se for estimativa, marca como estimativa.
Se for confirmado pelo usuário, marca como confirmado.
```

O usuário pode informar dados por:

- texto;
- áudio;
- foto de nota fiscal;
- formulário;
- correção posterior.

A IA deve extrair informações e perguntar o que falta.

Exemplo:

```txt
Usuário:
Comprei 1 kg de farinha por 5 reais e usei 800 gramas para fazer pão sovado.

IA:
Entendi. Essa receita rendeu quantos pães sovados?
```

Antes de salvar, a IA precisa pedir confirmação.

---

### 19.8 Correções por voz

O usuário precisa conseguir corrigir informações naturalmente.

Exemplo:

```txt
Usei 1 kg de farinha.
Na verdade, foram 800 gramas.
```

O sistema deve entender que a informação anterior precisa ser substituída, mas deve confirmar antes de salvar.

Exemplo:

```txt
Entendi. Vou corrigir a farinha de 1 kg para 800 g. Está correto?
```

---

### 19.9 Foto de nota fiscal ou recibo

No futuro, o usuário pode mandar foto da nota.

O sistema pode tentar extrair itens e preços, mas precisa confirmar tudo antes de salvar.

Exemplo:

```txt
Identifiquei estes itens na nota:

Farinha 1 kg — R$ 5,00
Leite 1 L — R$ 6,00
Ovos 12 unidades — R$ 12,00

Está correto?
```

Se a imagem estiver ruim, deve avisar:

```txt
Não consegui ler todos os itens com segurança. Pode confirmar manualmente?
```

---

## 20. Refatoração da arquitetura do back-end

O back-end também precisa ser revisado.

A revisão deve observar:

- organização de camadas;
- controllers;
- services;
- repositories;
- models;
- DTOs;
- validações;
- autenticação;
- autorização;
- tratamento de erros;
- regras de negócio;
- nomes de endpoints;
- padronização de respostas;
- estrutura para IA;
- estrutura de custo;
- histórico de alterações;
- testes;
- documentação de API.

O objetivo é deixar o back-end previsível, seguro e preparado para evolução.

---

## 21. Sugestão de arquitetura desejada

A arquitetura final pode seguir algo semelhante a:

```txt
src/
  controllers/
  services/
  repositories/
  models/
  dto/
  middlewares/
  auth/
  modules/
    produtos/
    vendas/
    catalogo/
    resumo/
    historico/
    perfil/
    ia/
    custos/
  utils/
  config/
  tests/
```

Essa estrutura deve ser adaptada à tecnologia real do projeto.

A ideia principal é separar:

- entrada HTTP;
- regra de negócio;
- acesso a dados;
- validação;
- autenticação;
- resposta para o front-end.

---

## 22. Tecnologias

Este README deve ser atualizado com as tecnologias reais do projeto.

Preencher conforme o projeto atual:

```txt
Linguagem:
Framework:
Banco de dados:
ORM/ODM:
Autenticação:
Testes:
Gerenciador de pacotes:
Ambiente:
Deploy:
```

---

## 23. Panorama futuro do back-end

O back-end deve evoluir para ser a base de um sistema simples de apoio à decisão para a padaria.

No futuro, o sistema deve ajudar a responder:

- quanto vendemos hoje?
- quanto vendemos no mês?
- o que mais vende?
- o que mais sobra?
- o que devemos produzir menos?
- o que devemos produzir mais?
- qual produto dá mais lucro?
- qual produto custa mais caro para produzir?
- existe padrão por dia da semana?
- a produção está acima ou abaixo do ideal?

---

## 24. Tarefa atual  ---- INICIAR AQUI

A tarefa atual é documentar o projeto.

Antes de implementar novas funcionalidades, o back-end precisa ter este README como referência.

Não implementar agora sem antes alinhar o plano geral, a arquitetura e as regras de negócio.
