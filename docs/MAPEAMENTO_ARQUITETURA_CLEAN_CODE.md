# Mapeamento de arquitetura e clean code

Data do levantamento: apos `git pull` em `main`, sem novidades remotas.

## Resumo executivo

O projeto esta bem encaminhado na borda HTTP: os `router.py` sao, em geral, finos e delegam para servicos. O gargalo arquitetural esta nos `servico.py`, que acumulam regra de negocio, acesso direto ao Supabase, composicao de resposta, integracoes externas, parse de IA, persistencia de historico e detalhes de infraestrutura.

Prioridade maxima:

1. Quebrar `custos` e `ia` em casos de uso, repositorios e componentes de dominio.
2. Extrair repositorios Supabase por agregado/tabela.
3. Criar testes automatizados antes de mexer nos fluxos financeiros, IA e dia fechado.
4. Padronizar autenticacao/autorizacao por dependencia FastAPI, removendo excecoes dispersas.
5. Centralizar tempo, transacoes logicas, historico e tratamento de resposta vazia do Supabase.

## Metricas de tamanho

Pacotes mais pesados:

| Pacote | Linhas | Principal risco |
| --- | ---: | --- |
| `app.modules.custos` | 4648 | assistente, calculo, IA, compras, receitas e persistencia no mesmo modulo |
| `app.modules.ia` | 2498 | interpretacao, confirmacao, analise, fallback e execucao misturados |
| `app.modules.dias_de_venda` | 1293 | abertura, fechamento, sobras e correcao retroativa no mesmo servico |
| `app.modules.admin` | 829 | seed de dados com geracao, limpeza e persistencia acopladas |
| `app.modules.relatorios` | 714 | consulta, agregacao e formato de resposta no mesmo fluxo |
| `app.modules.auth` | 570 | auth real convivendo com modo sem token e API key global |

Arquivos criticos:

| Arquivo | Linhas | Observacao |
| --- | ---: | --- |
| `app/modules/custos/assistente_servico.py` | 2670 | maior arquivo; mistura sessao, rascunho, IA, simulacao, normalizacao e confirmacao |
| `app/modules/ia/servico.py` | 2289 | orquestrador de IA tambem executa operacoes reais de venda/producao |
| `app/modules/custos/servico.py` | 1410 | calculo, cadastro de insumo, nota, compras e lista de compras juntos |
| `app/modules/dias_de_venda/servico.py` | 1052 | ciclo de dia e correcao retroativa com muitas regras acopladas |
| `app/modules/admin/seed_servico.py` | 705 | gerador de dados fake com varias responsabilidades |

## Arquitetura alvo

Modelo incremental recomendado:

```txt
app/
  api/
    router.py
  core/
    config.py
    errors.py
    clock.py
    security.py
  db/
    supabase.py
    openai.py
    result.py
  modules/
    produtos/
      router.py
      schemas.py
      use_cases.py
      repository.py
      pricing.py
      events.py
    vendas/
      router.py
      schemas.py
      use_cases.py
      repository.py
      availability.py
    dias_de_venda/
      router.py
      schemas.py
      use_cases.py
      repository.py
      leftovers.py
      corrections.py
    custos/
      router.py
      schemas.py
      repositories.py
      use_cases/
      domain/
      assistant/
      integrations/
    ia/
      router.py
      schemas.py
      use_cases.py
      interpreter.py
      confirmation.py
      analytics.py
      prompts.py
      fallback_parser.py
  shared/
    schemas.py
    timeline.py
    money.py
    units.py
  tests/
```

Regras da nova arquitetura:

- `router.py`: apenas HTTP, dependencias, status code e response model.
- `use_cases.py`: orquestracao da regra de negocio.
- `repository.py`: todas as chamadas Supabase do modulo.
- `domain/`: calculos puros, normalizadores, validadores e entidades de dominio.
- `integrations/`: OpenAI, storage, OCR, audio, nota fiscal e servicos externos.
- `events.py` ou `timeline.py`: nomes de eventos, payloads e registro de linha do tempo.
- Testes unitarios focam dominio puro; testes de integracao focam use cases com repositorio fake.

## Problemas transversais

### Acesso direto ao Supabase

Hoje quase todo servico chama `get_supabase_client()` e encadeia `.table(...).select/insert/update`. Isso dificulta teste, troca de infra, mock e controle de erros.

Melhoria:

- criar repositorios por modulo;
- padronizar `insert_one`, `update_one`, `select_one_or_none`, `select_many`;
- tratar `data[0]` vazio em um helper unico;
- nomear consultas por intencao de negocio, nao por tabela.

### Tempo e datas

Ha uso direto de `date.today()` e `datetime.now(UTC)` em varios modulos. Como o negocio usa data operacional, isso precisa ser centralizado.

Melhoria:

- criar `app/core/clock.py`;
- usar `data_operacional_hoje()` onde a regra for de padaria;
- manter `datetime.now(UTC)` apenas em infra/auditoria, por helper.

### Autenticacao e autorizacao

Existe API key global em middleware, auth por bearer, modo sem token e excecoes de rota no `main.py`.

Melhoria:

- remover lista de rotas isentas do `main.py` gradualmente;
- colocar protecao por router/dependencia;
- explicitar dependencias `Publico`, `UsuarioAtual`, `Admin`, `Dono`;
- proteger `GET /auth/usuarios` e `PATCH /auth/usuarios/{id}/papel`;
- remover `USUARIO_SISTEMA_SEM_AUTH` das notificacoes admin.

### Eventos e historico

`registrar_evento_na_linha_do_tempo` e chamado de muitos lugares, com strings livres.

Melhoria:

- criar enum/constantes de eventos;
- criar builders de payload por evento;
- garantir que evento esteja dentro do mesmo caso de uso da mutacao;
- testar payloads de auditoria nos fluxos sensiveis.

### Testes

Nao ha suite automatizada. Isso e o maior risco para refatorar.

Melhoria:

- adicionar `pytest`, `pytest-asyncio` e fixtures de repositorios fake;
- cobrir primeiro: preco vigente, venda, fechamento de dia, correcao retroativa, calculo de custo e confirmacao de IA;
- usar testes de contrato para schemas publicos.

### Lint e higiene

`python -m compileall app` passou. `python -m ruff check .` encontrou 4 itens:

- imports em `app/core/config.py`;
- imports em `app/db/supabase.py`;
- dois defaults com `Query(...)` em `app/modules/historico/router.py`.

## Mapa pacote a pacote

### `app.main`

Estado atual:

- cria a app, CORS, handlers, middleware de API key e healthcheck;
- contem lista manual de rotas isentas.

Melhorias:

- mover seguranca HTTP para `app/core/security.py`;
- transformar isencao de rota em dependencias explicitas nos routers;
- deixar `create_app` apenas montando middleware, handlers e routers;
- revisar `allow_credentials=True` com `allow_origins=["*"]` para deploy real.

Prioridade: alta.

### `app.api`

Estado atual:

- agregador de routers, simples e adequado.

Melhorias:

- manter como composition root;
- ordenar routers por dominio ou alfabetico;
- considerar versoes futuras em `api/v1/router.py` se a API crescer.

Prioridade: baixa.

### `app.core`

Estado atual:

- configuracao e erros globais;
- `Settings` mistura propriedades de Supabase, OpenAI, API key e CORS.

Melhorias:

- separar `security.py`, `clock.py` e talvez `pagination.py`;
- adicionar erro `UnauthorizedError`, `ForbiddenError`, `ValidationError` de dominio;
- padronizar conversao de erros externos;
- evitar imports marcados como OpenAI por causa de nomes de campos de config.

Prioridade: media.

### `app.db`

Estado atual:

- factories cacheadas para Supabase e OpenAI.

Melhorias:

- criar wrappers finos para resposta Supabase;
- permitir injecao de cliente em testes;
- separar cliente anonimo e service-role se o front/API exigir politicas diferentes;
- padronizar tratamento de config ausente.

Prioridade: alta.

### `app.shared`

Estado atual:

- helpers de serializacao, datas, schemas, slugs e linha do tempo.

Melhorias:

- renomear arquivos para padrao unico se o projeto aceitar ingles ou portugues;
- mover unidades/decimal/money para helpers compartilhados;
- substituir strings soltas de eventos por constantes;
- manter `shared` apenas com utilitarios realmente transversais.

Prioridade: media.

### `app.modules.produtos`

Estado atual:

- modulo saudavel, mas ainda mistura produto, preco, slug, historico e Supabase no mesmo servico.

Melhorias:

- extrair `repository.py` com `ProdutoRepository` e `PrecoProdutoRepository`;
- extrair `pricing.py` para vigencia de preco;
- testar insercao de preco entre duas vigencias;
- trocar `date.today()` por helper de data;
- criar contrato claro para snapshot de produto/preco usado por vendas e producao.

Prioridade: alta, porque outros modulos dependem deste contrato.

### `app.modules.vendas`

Estado atual:

- registra venda, cancela, anexa itens e calcula esgotamento;
- depende de `dias_de_venda` e `produtos`.

Melhorias:

- extrair `availability.py` para disponibilidade, sobra usada e esgotamento;
- extrair repositorio de venda e item de venda;
- adicionar validacao explicita de estoque antes de vender, se a regra do produto exigir;
- padronizar cancelamento como evento de dominio;
- garantir idempotencia em confirmacoes vindas da IA.

Prioridade: alta.

### `app.modules.dias_de_venda`

Estado atual:

- concentra abertura, inicio do dia, fechamento, sobras, producao e correcao retroativa.

Melhorias:

- dividir em `opening.py`, `production.py`, `closing.py`, `leftovers.py`, `corrections.py`;
- manter `use_cases.py` orquestrando esses componentes;
- criar `DiaDeVendaRepository`;
- isolar regras de sobras em funcoes puras;
- isolar correcao retroativa com objetos `AlteracaoDiaFechado`;
- adicionar testes de: dia ja aberto, dia anterior aberto, dia fechado com sobra, correcao sem alteracao, venda retroativa e cancelamento retroativo.

Prioridade: alta.

### `app.modules.relatorios`

Estado atual:

- le diretamente varias tabelas e consolida dia/periodo no mesmo arquivo.

Melhorias:

- separar `queries.py` de `aggregations.py`;
- reutilizar uma view/projecao de resumo de dia quando existir;
- manter agregadores puros testaveis sem Supabase;
- evitar N+1 ao buscar periodo chamando resumo por data repetidamente;
- criar modelos internos para resumo antes do response dict.

Prioridade: alta.

### `app.modules.ia`

Estado atual:

- arquivo unico com interpretacao, prompt OpenAI, fallback local, analise, transcricao, persistencia da interacao e execucao da operacao confirmada.

Melhorias:

- dividir em:
  - `interpreter.py`: OpenAI + schema de interpretacao;
  - `fallback_parser.py`: parser local;
  - `confirmation.py`: monta dados de confirmacao;
  - `executor.py`: aplica operacoes confirmadas chamando casos de uso reais;
  - `analytics.py`: dados estruturados e analises;
  - `prompts.py`: textos de sistema e schemas JSON;
  - `repository.py`: `interacoes_ia`;
- nunca deixar parser de IA conhecer detalhes de Supabase;
- comandos confirmados devem chamar use cases de vendas/dias, nao funcoes internas;
- trocar `date.today()` por clock injetavel;
- testar fallback parser e normalizacao sem OpenAI.

Prioridade: altissima.

### `app.modules.custos`

Estado atual:

- maior area do sistema;
- `servico.py` mistura insumos, receitas, precos de compra, nota, calculo e lista de compras;
- `assistente_servico.py` mistura sessao, rascunho, normalizacao, simulacao, IA, audio/imagem, perguntas e confirmacao.

Melhorias:

- dividir `custos` em subpacotes:

```txt
custos/
  router.py
  schemas.py
  repositories.py
  domain/
    units.py
    money.py
    ingredient_matching.py
    cost_calculator.py
    purchase_price.py
  use_cases/
    insumos.py
    receitas.py
    calculo.py
    compras.py
    listas_compras.py
  assistant/
    sessions.py
    draft.py
    extraction.py
    questions.py
    simulation.py
    confirmation.py
  integrations/
    openai_extractor.py
    media_reader.py
```

- mover `UNIDADES_BASE` e descricoes para dominio compartilhado;
- transformar simulacao e calculo em funcoes puras;
- separar extracao OpenAI de normalizacao deterministica;
- adicionar `Decimal` consistente nos schemas/respostas;
- criar testes de unidade para conversao de unidades e matching de insumos;
- criar testes de integracao para confirmar sessao de custeio.

Prioridade: altissima.

### `app.modules.auth`

Estado atual:

- registro, login, sessao, perfil e papeis no mesmo servico;
- algumas rotas sensiveis nao exigem papel no router;
- fallback sem token da permissao de dono.

Melhorias:

- separar `sessions.py`, `users.py`, `profiles.py`, `permissions.py`;
- aplicar `Depends(exigir_papel("administrador", "dono"))` em gestao de usuarios;
- tornar modo sem token configuravel e limitado a ambiente local;
- criar politicas de expiracao e limpeza de sessao;
- adicionar testes para login, token expirado, papel insuficiente e troca de senha.

Prioridade: alta.

### `app.modules.midia`

Estado atual:

- upload para Supabase Storage e registro em tabela.

Melhorias:

- criar `storage.py` para bucket/path/content-type;
- validar tamanho e tipo de arquivo;
- padronizar path por entidade;
- permitir repositorio fake em testes;
- separar "definir como principal" por entidade, pois produto e usuario tem regras diferentes.

Prioridade: media.

### `app.modules.notificacoes`

Estado atual:

- modulo pequeno, mas admin esta sem dependencia real e usa usuario fixo sem auth.

Melhorias:

- proteger rotas admin;
- mover usuario do sistema para auth/dependencias ou remover;
- criar repositorio;
- padronizar status como enum;
- validar midias associadas a notificacao.

Prioridade: alta por seguranca.

### `app.modules.rag`

Estado atual:

- protegido por admin real;
- cria documento e quebra trechos, mas ainda nao indexa embeddings.

Melhorias:

- separar chunking de persistencia;
- preparar interface de indexador;
- versionar documentos e reindexacao;
- testar chunking;
- nao acoplar futuras rotinas de OpenAI ao servico atual.

Prioridade: media.

### `app.modules.admin`

Estado atual:

- seed de vendas fake e produtos fake em servico grande.

Melhorias:

- limitar a ambiente local/desenvolvimento;
- separar geracao fake de persistencia;
- criar factories deterministicas com seed controlavel;
- evitar que regra de negocio real dependa de dados fake;
- cobrir com teste leve de geracao.

Prioridade: media.

### `app.modules.locais`

Estado atual:

- modulo simples e adequado.

Melhorias:

- extrair repositorio quando padrao for adotado;
- validar unicidade de nome se for regra de negocio;
- manter como referencia de modulo pequeno.

Prioridade: baixa.

### `app.modules.historico`

Estado atual:

- consulta linha do tempo;
- router tem dois alertas Ruff por `Query(...)` em default.

Melhorias:

- corrigir defaults com `Annotated`;
- criar filtros tipados;
- padronizar evento publico com enum;
- adicionar paginacao/cursor se a linha do tempo crescer.

Prioridade: baixa/media.

## Ordem de execucao recomendada

### Fase 0: seguranca para refatorar

1. Adicionar pytest e fixtures.
2. Corrigir Ruff basico.
3. Criar helpers de Supabase result.
4. Criar clock central.
5. Cobrir testes de produto/preco, venda e dia de venda.

### Fase 1: contratos centrais

1. Extrair repositorios de `produtos`, `vendas` e `dias_de_venda`.
2. Extrair regra de preco vigente.
3. Extrair disponibilidade/sobras.
4. Extrair eventos de linha do tempo.

### Fase 2: IA

1. Separar parser OpenAI, fallback, confirmacao e executor.
2. Garantir que IA so interprete e confirme; execucao fica nos use cases.
3. Testar comandos de venda, producao, cancelamento e desconhecido.

### Fase 3: Custos

1. Extrair dominio puro de unidades, matching e calculo.
2. Separar cadastros de insumos/receitas/compras/listas.
3. Separar assistente em session/draft/extraction/questions/simulation/confirmation.
4. Criar testes para calculo e confirmacao do assistente.

### Fase 4: seguranca e permissao

1. Remover excecoes de API key do `main.py`.
2. Proteger admin/notificacoes e auth/usuarios.
3. Tornar modo sem token apenas local.
4. Documentar matriz de permissao por endpoint.

## Definition of done para clean code

Uma refatoracao so deve ser considerada pronta quando:

- arquivos de servico ficarem preferencialmente abaixo de 300-500 linhas;
- funcoes criticas ficarem abaixo de 40-60 linhas ou tiverem subpassos nomeados;
- regra de negocio puder ser testada sem Supabase/OpenAI;
- acesso a dados estiver em repositorios;
- OpenAI estiver atras de interface/adaptador;
- todos os endpoints sensiveis tiverem dependencia de permissao clara;
- `ruff check .` e `python -m compileall app` passarem;
- fluxos centrais tiverem testes automatizados.
