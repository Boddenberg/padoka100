# Plano de rearquitetura moderna

Este plano ignora a arquitetura sugerida no README atual e parte do estado real
do codigo. O objetivo e transformar o backend em uma base pequena por dentro,
facil de manter, facil de testar e especialmente facil para uma IA entender sem
precisar ler arquivos de milhares de linhas.

## Objetivo

Construir uma arquitetura moderna para FastAPI/Python baseada em:

- modulos pequenos por contexto de negocio;
- casos de uso explicitos;
- dominio testavel sem Supabase, OpenAI ou FastAPI;
- adaptadores para banco, storage e IA;
- contratos publicos claros entre modulos;
- arquivos e funcoes curtos;
- testes automatizados antes das grandes cirurgias;
- documentacao local para humanos e agentes de IA.

Nao vamos fazer um "big bang". A migracao precisa ser incremental, sempre com o
sistema funcionando.

## Diagnostico atual

O problema principal nao e FastAPI, nem Supabase, nem o uso de modulos em
portugues. O problema e que os servicos viraram arquivos que concentram quase
tudo:

- regra de negocio;
- query Supabase;
- formato de resposta;
- integracao OpenAI;
- parse de texto/audio/imagem;
- historico;
- validacao;
- fallback;
- operacao confirmada;
- detalhes de data/hora;
- regras financeiras.

Maiores pontos de atencao:

| Area | Arquivo | Linhas | Problema |
| --- | ---: | ---: | --- |
| Custos assistidos | `app/modules/custos/assistente_servico.py` | 2670 | sessao, rascunho, IA, simulacao e confirmacao juntos |
| IA | `app/modules/ia/servico.py` | 2289 | interpretar, analisar, confirmar e executar no mesmo arquivo |
| Custos | `app/modules/custos/servico.py` | 1410 | insumos, receitas, compras, nota, calculo e lista juntos |
| Dia de venda | `app/modules/dias_de_venda/servico.py` | 1052 | abertura, fechamento, sobras e correcao no mesmo fluxo |
| Seed admin | `app/modules/admin/seed_servico.py` | 705 | geracao fake e persistencia acopladas |

## Arquitetura alvo

Usaremos uma arquitetura hibrida:

- Vertical Slice Architecture para organizar por contexto de negocio.
- Clean/Hexagonal Architecture dentro dos contextos complexos.
- Command/Query separation onde fizer sentido.
- Ports and adapters para banco, OpenAI, storage e servicos externos.

Em portugues simples: cada area do negocio fica em um pacote proprio; dentro
dela, HTTP chama caso de uso, caso de uso chama dominio e portas, adaptadores
implementam Supabase/OpenAI/Storage.

Fluxo ideal:

```txt
HTTP Router
  -> Use Case
    -> Domain services / pure functions
    -> Ports
      -> Supabase adapter
      -> OpenAI adapter
      -> Storage adapter
  -> Response schema
```

O router nunca fala com Supabase.
O dominio nunca importa FastAPI, Supabase ou OpenAI.
A IA nunca executa mutacao direto; ela interpreta e monta intencao.
A execucao real sempre passa por um caso de uso de negocio.

## Estrutura alvo

```txt
app/
  main.py
  api/
    v1/
      router.py
      dependencies.py

  core/
    config.py
    errors.py
    clock.py
    security.py
    logging.py
    pagination.py

  infra/
    supabase/
      client.py
      result.py
      unit_of_work.py
    openai/
      client.py
      responses.py
    storage/
      supabase_storage.py

  shared/
    domain/
      money.py
      units.py
      ids.py
      dates.py
    events/
      timeline.py
      event_types.py
    schemas/
      base.py

  modules/
    catalogo/
      api.py
      schemas.py
      use_cases/
      domain/
      ports.py
      adapters/

    vendas/
      api.py
      schemas.py
      use_cases/
      domain/
      ports.py
      adapters/

    dias_de_venda/
      api.py
      schemas.py
      use_cases/
      domain/
      ports.py
      adapters/

    custos/
      api.py
      schemas.py
      use_cases/
      domain/
      assistant/
      ports.py
      adapters/

    ia/
      api.py
      schemas.py
      use_cases/
      domain/
      prompts/
      ports.py
      adapters/

    relatorios/
      api.py
      schemas.py
      use_cases/
      projections/
      ports.py
      adapters/

    auth/
      api.py
      schemas.py
      use_cases/
      domain/
      ports.py
      adapters/

  tests/
    unit/
    integration/
    contract/
    fixtures/
```

Nao precisa renomear tudo no primeiro passo. Podemos criar o novo padrao nos
modulos que forem sendo refatorados e manter compatibilidade via imports finos.

## Regras de organizacao

### Limites de tamanho

- Arquivo comum: ate 300 linhas.
- Arquivo complexo: ate 500 linhas, com justificativa.
- Funcao comum: ate 40 linhas.
- Funcao complexa: ate 70 linhas, com subpassos nomeados.
- Prompt/schema grande: arquivo proprio em `prompts/`.
- Constantes grandes: arquivo proprio em `domain/constants.py` ou similar.

### Regras de dependencia

Permitido:

```txt
api -> use_cases -> domain
api -> schemas
use_cases -> ports
use_cases -> domain
adapters -> ports
adapters -> infra
```

Proibido:

```txt
domain -> FastAPI
domain -> Supabase
domain -> OpenAI
domain -> UploadFile
domain -> app.modules.outro_modulo.servico interno
```

### Contratos entre modulos

Cada modulo deve expor um facade pequeno para outros modulos.

Exemplo:

```txt
catalogo/public.py
  buscar_produto_snapshot(...)
  buscar_preco_vigente(...)
  listar_produtos_ativos(...)
```

Outros modulos nao devem importar helpers privados nem servicos enormes.

## Padrao interno de modulo

Modulo simples:

```txt
modulo/
  api.py
  schemas.py
  use_cases.py
  domain.py
  ports.py
  adapters.py
```

Modulo complexo:

```txt
modulo/
  api.py
  schemas/
    requests.py
    responses.py
  use_cases/
    criar_x.py
    atualizar_x.py
    listar_x.py
  domain/
    entities.py
    rules.py
    services.py
    errors.py
  ports.py
  adapters/
    supabase_repository.py
```

## Padroes de codigo

### Use cases

Cada mutacao importante vira um caso de uso pequeno e nomeado:

```txt
RegistrarVenda
CancelarVenda
AbrirDiaDeVenda
FecharDiaDeVenda
ConfirmarComandoDeIA
CalcularCustoProduto
ConfirmarSessaoCusteio
```

Eles recebem dependencias por construtor/factory ou parametros explicitos. Em
FastAPI, as dependencias podem ser montadas em `api/dependencies.py`.

### Repositorios

Cada repositorio fala com tabelas especificas e devolve objetos/dicts de
contrato interno.

Nao usar `.execute().data[0]` espalhado. Criar helpers:

```txt
one_or_none(result)
one_or_raise(result, resource, id)
many(result)
insert_one(query)
update_one(query)
```

### Dominio puro

Tudo que for calculo, decisao, consolidacao, normalizacao e validacao de regra
de negocio deve poder rodar sem rede.

Exemplos:

- calcular preco vigente entre versoes;
- calcular sobra;
- calcular disponibilidade;
- calcular custo por ingrediente;
- consolidar status de custo;
- normalizar unidade;
- detectar intencao local de IA;
- montar perguntas pendentes do assistente.

### IA

IA precisa ser uma camada interpretadora, nao uma camada dona do negocio.

Separacao obrigatoria:

```txt
ia/
  domain/
    intent.py
    confirmation.py
  prompts/
    command_interpreter.md
    sales_analysis.md
  adapters/
    openai_command_interpreter.py
    openai_audio_transcriber.py
  use_cases/
    interpretar_comando.py
    confirmar_comando.py
    analisar_periodo.py
```

Regra: interpretacao gera uma intencao estruturada. Confirmacao transforma a
intencao em chamada de caso de uso real. A IA nao deve conhecer Supabase.

### Prompts e schemas de IA

Prompts grandes devem sair do Python.

Formato sugerido:

```txt
prompts/
  command_interpreter.system.md
  command_interpreter.schema.json
  cost_extractor.system.md
  cost_extractor.schema.json
```

Isso facilita revisao humana e entendimento por IA.

### Erros

Criar erros especificos por dominio quando melhorar clareza:

```txt
ProdutoSemPrecoVigente
DiaDeVendaFechado
EstoqueInsuficiente
SessaoCusteioImutavel
ConfirmacaoIAExpirada
```

Na borda, esses erros viram `AppError`/HTTP. No dominio, eles sao regras.

### Datas

Criar `core/clock.py`:

```txt
hoje_operacional()
agora_utc()
data_atual_para_preco()
```

Nada de `date.today()` solto em regra de negocio.

### Eventos

Eventos de linha do tempo devem ser tipados:

```txt
TimelineEventType.VENDA_REALIZADA
TimelineEventType.DIA_VENDA_ABERTO
TimelineEventType.CUSTO_PRODUTO_CONFIRMADO
```

Cada use case decide qual evento emitir. Payload de evento tambem deve ter
builder pequeno e testavel.

## Pacote por pacote

### `core`

Criar:

- `clock.py`: fonte unica de tempo;
- `security.py`: regras globais de API key/bearer;
- `logging.py`: logs estruturados;
- `pagination.py`: padrao de limite/cursor;
- erros especificos e conversao para HTTP.

Primeiro ataque:

- remover regra de rota isenta de dentro do `main.py`;
- centralizar auth por dependencia;
- manter `main.py` pequeno.

### `infra`

Novo pacote para detalhes tecnicos:

- Supabase client;
- helpers de resposta Supabase;
- OpenAI client;
- storage;
- unit of work logico.

Supabase nao precisa sumir. Ele so precisa ficar atras de adaptadores.

### `shared`

Deve conter apenas coisas transversais e estaveis:

- dinheiro;
- unidades;
- datas;
- eventos;
- schemas base;
- ids;
- serializacao.

Evitar colocar regra especifica de custos/vendas em `shared`.

### `catalogo` / produtos

Responsabilidades:

- produto;
- versoes de preco;
- snapshot de produto/preco;
- slug.

Extracoes:

- `domain/pricing.py`: vigencia de preco;
- `use_cases/criar_produto.py`;
- `use_cases/criar_versao_preco.py`;
- `public.py`: snapshot e preco vigente para outros modulos;
- `adapters/supabase_catalogo_repository.py`.

Testes essenciais:

- criar preco inicial;
- inserir preco entre duas vigencias;
- buscar preco vigente;
- snapshot para data historica;
- slug unico.

### `vendas`

Responsabilidades:

- registrar venda;
- cancelar venda;
- item de venda;
- disponibilidade no dia;
- esgotamento.

Extracoes:

- `domain/availability.py`;
- `domain/sale_totals.py`;
- `use_cases/registrar_venda.py`;
- `use_cases/cancelar_venda.py`;
- `ports.py` para catalogo e dia de venda;
- `adapters/supabase_vendas_repository.py`.

Testes essenciais:

- venda normal;
- venda em dia fechado bloqueada;
- venda retroativa permitida apenas por caso de uso especifico;
- cancelamento idempotente;
- evento de produto esgotado;
- total de venda/custo.

### `dias_de_venda`

Responsabilidades:

- abrir dia;
- iniciar dia operacional;
- salvar producao;
- fechar dia;
- decidir sobras;
- corrigir dia fechado.

Extracoes:

- `domain/leftovers.py`;
- `domain/day_status.py`;
- `domain/corrections.py`;
- `use_cases/iniciar_dia.py`;
- `use_cases/fechar_dia.py`;
- `use_cases/corrigir_dia_fechado.py`;
- `adapters/supabase_dia_repository.py`.

Testes essenciais:

- iniciar sem dia anterior;
- iniciar com dia anterior aberto;
- iniciar com sobra pendente;
- decisao parcial de sobra;
- fechamento;
- correcao retroativa com auditoria;
- correcao sem alteracao deve falhar.

### `relatorios`

Responsabilidades:

- montar leituras;
- consolidar periodo;
- consolidar produto/dia;
- entregar resposta para front e IA.

Extracoes:

- `projections/daily_sales_projection.py`;
- `domain/aggregation.py`;
- `use_cases/buscar_resumo_dia.py`;
- `use_cases/buscar_resumo_periodo.py`;
- queries Supabase em adapter.

Melhoria importante:

- evitar N+1 em periodo;
- usar agregadores puros testaveis;
- ter uma estrutura intermediaria de resumo antes do dict final.

### `ia`

Responsabilidades:

- transcrever;
- interpretar comando;
- gerar confirmacao;
- confirmar comando;
- analisar dados estruturados.

Extracoes:

- `domain/intent.py`;
- `domain/fallback_parser.py`;
- `domain/confirmation_message.py`;
- `use_cases/interpretar_comando.py`;
- `use_cases/confirmar_comando.py`;
- `use_cases/analisar_periodo.py`;
- `adapters/openai_interpreter.py`;
- `adapters/openai_analyzer.py`;
- `adapters/supabase_interacao_repository.py`;
- prompts e schemas em arquivos separados.

Regra principal:

- IA nao executa venda/producao/cancelamento diretamente.
- IA gera intencao.
- Confirmacao chama use cases reais.

Testes essenciais:

- fallback parser;
- normalizacao de produto;
- comando desconhecido;
- cancelamento sem alvo claro;
- confirmacao idempotente;
- erro de use case vira falha de confirmacao;
- analise local sem OpenAI.

### `custos`

Responsabilidades:

- insumos;
- precos de insumo;
- receitas;
- custos adicionais;
- calculo de custo;
- lista de compras;
- extracao de nota;
- assistente de custeio.

Precisa virar subarquitetura propria:

```txt
custos/
  api.py
  schemas/
  domain/
    units.py
    ingredient_matching.py
    purchase_price.py
    recipe_cost.py
    cost_status.py
    shopping_list.py
  use_cases/
    criar_insumo.py
    registrar_preco_insumo.py
    criar_receita.py
    calcular_custo_produto.py
    gerar_lista_compras.py
    atualizar_precos_por_compra.py
  assistant/
    sessions.py
    draft.py
    extraction.py
    questions.py
    simulation.py
    confirmation.py
  adapters/
    supabase_custos_repository.py
    openai_cost_extractor.py
```

Primeira meta: tirar todo calculo e normalizacao para dominio puro.

Testes essenciais:

- conversao de unidade;
- matching de ingrediente;
- custo de ingrediente;
- custo total de receita;
- status consolidado;
- lista de compras;
- rascunho do assistente;
- perguntas pendentes;
- confirmacao de sessao.

### `auth`

Responsabilidades:

- usuario;
- sessao;
- login/logout;
- perfil;
- permissao.

Extracoes:

- `domain/passwords.py`;
- `domain/roles.py`;
- `use_cases/login.py`;
- `use_cases/registrar_usuario.py`;
- `use_cases/trocar_senha.py`;
- `use_cases/atualizar_perfil.py`;
- `dependencies.py` para `UsuarioAtual`, `Admin`, `Dono`.

Mudancas:

- admin real em rotas sensiveis;
- modo sem token limitado a ambiente local;
- API key tratada como credencial de sistema, nao como bypass espalhado.

### `midia`

Responsabilidades:

- validar arquivo;
- subir storage;
- persistir midia;
- definir principal quando aplicavel.

Extracoes:

- `domain/file_validation.py`;
- `adapters/supabase_storage.py`;
- `use_cases/enviar_midia.py`.

### `notificacoes`

Responsabilidades:

- notificacoes publicas;
- notificacoes admin;
- anexos.

Mudancas:

- proteger admin;
- remover usuario fake sem auth;
- status como enum;
- repositorio separado.

### `rag`

Responsabilidades:

- documentos;
- chunking;
- futura indexacao.

Mudancas:

- separar chunking puro;
- criar porta `DocumentIndexer`;
- deixar OpenAI/embedding como adapter futuro.

### `admin`

Responsabilidades:

- operacoes administrativas e seed.

Mudancas:

- seed so em ambiente local/dev;
- factories deterministicas;
- persistencia separada da geracao.

## Plano de execucao

### Fase 0: base de seguranca

Objetivo: poder refatorar sem medo.

Entregas:

1. Adicionar `pytest` e estrutura `tests/`.
2. Corrigir Ruff atual.
3. Adicionar check de limite de tamanho de arquivo/funcoes ou ao menos script de relatorio.
4. Criar `core/clock.py`.
5. Criar helpers de resposta Supabase.
6. Criar primeiros testes de dominio para `produtos`, `vendas` e `dias_de_venda`.

Criterio de pronto:

- `ruff check .` passa;
- `compileall` passa;
- primeira suite de testes passa;
- nenhum comportamento externo mudou.

### Fase 1: contratos centrais

Objetivo: criar padrao novo em modulos menores antes dos gigantes.

Ordem:

1. Refatorar `produtos` para `catalogo`.
2. Extrair preco vigente e snapshot.
3. Criar facade publico de catalogo.
4. Refatorar `vendas` para use cases + availability.
5. Refatorar partes centrais de `dias_de_venda`.

Criterio de pronto:

- vendas e dias dependem de contrato publico de catalogo;
- dominio principal testado sem Supabase;
- arquivos novos pequenos.

### Fase 2: dia de venda e relatorios

Objetivo: estabilizar o coracao operacional.

Entregas:

1. Separar abertura, fechamento, sobras e correcao.
2. Criar agregadores puros para relatorios.
3. Remover N+1 mais obvio em resumo por periodo.
4. Testar correcao retroativa e sobras.

Criterio de pronto:

- `dias_de_venda` deixa de ter servico gigante;
- relatorios usam queries/projections separadas;
- fluxos historicos continuam compativeis.

### Fase 3: IA

Objetivo: tornar IA compreensivel e segura.

Entregas:

1. Extrair prompts e schemas JSON.
2. Separar OpenAI interpreter do fallback parser.
3. Separar montagem de confirmacao.
4. Separar executor de confirmacao.
5. Fazer executor chamar use cases reais.
6. Testar interpretacao e confirmacao sem OpenAI.

Criterio de pronto:

- `ia/servico.py` some ou vira facade fino;
- IA nao importa repositorios Supabase diretamente;
- confirmacao e idempotencia testadas.

### Fase 4: custos

Objetivo: desmontar o maior bloco do sistema.

Ordem:

1. Extrair dominio de unidades e dinheiro.
2. Extrair matching de ingrediente.
3. Extrair calculadora de custo.
4. Extrair lista de compras.
5. Separar insumos/receitas/compras em use cases.
6. Separar assistente em session, draft, extraction, questions, simulation, confirmation.
7. Tirar prompts/schemas de extracao do Python.

Criterio de pronto:

- calculo de custo roda sem Supabase/OpenAI;
- assistente tem etapas pequenas;
- nenhum arquivo de custos passa de 500 linhas;
- fluxos principais cobertos por testes.

### Fase 5: auth, permissoes e borda HTTP

Objetivo: deixar seguranca explicita.

Entregas:

1. Dependencias `Publico`, `UsuarioAtual`, `Admin`, `Dono`.
2. Proteger rotas admin e gestao de usuarios.
3. Remover lista de rotas isentas do `main.py`.
4. Limitar modo sem token por config de ambiente.
5. Criar matriz de permissao por endpoint.

Criterio de pronto:

- nenhuma rota sensivel fica publica por acidente;
- `main.py` fica pequeno;
- auth testado.

### Fase 6: limpeza final

Objetivo: cortar legado.

Entregas:

1. Remover facades temporarios.
2. Remover imports antigos.
3. Atualizar docs.
4. Gerar mapa de dependencias.
5. Aplicar limite de tamanho em CI/local.
6. Criar ADRs das decisoes arquiteturais.

Criterio de pronto:

- arquitetura nova e padrao dominante;
- docs batem com codigo;
- uma IA consegue achar cada fluxo pelo nome do use case.

## Como atacar sem quebrar tudo

Para cada refatoracao:

1. Escrever teste do comportamento atual.
2. Extrair dominio puro primeiro.
3. Extrair repositorio/adaptador depois.
4. Trocar o servico antigo para chamar o use case novo.
5. Manter endpoint igual.
6. Rodar testes/lint.
7. So depois apagar codigo antigo.

Regra de ouro: primeiro envolver, depois mover, depois apagar.

## Backlog inicial sugerido

### Sprint 1

- Criar `tests/`.
- Adicionar pytest.
- Corrigir Ruff.
- Criar `core/clock.py`.
- Criar `infra/supabase/result.py`.
- Testar preco vigente de produto.
- Testar calculo de disponibilidade de venda.

### Sprint 2

- Extrair `catalogo/domain/pricing.py`.
- Extrair repositorio de produtos/precos.
- Criar `catalogo/public.py`.
- Trocar vendas/dias para usar contrato publico de catalogo.

### Sprint 3

- Extrair `vendas/domain/availability.py`.
- Criar `RegistrarVenda`.
- Criar `CancelarVenda`.
- Testar venda/cancelamento/esgotamento.

### Sprint 4

- Extrair sobras de `dias_de_venda`.
- Criar `IniciarDiaDeVenda`.
- Criar `FecharDiaDeVenda`.
- Testar decisao de sobra.

### Sprint 5

- Extrair prompts/schemas da IA.
- Criar fallback parser puro.
- Criar intent/confirmation.
- Testar confirmacao.

### Sprint 6+

- Comecar `custos/domain`.
- Extrair unidades.
- Extrair calculo de custo.
- Extrair assistente por etapas.

## Documentacao para IA

Criar arquivos pequenos e objetivos:

```txt
docs/ARCHITECTURE.md
docs/MODULE_MAP.md
docs/DEPENDENCY_RULES.md
docs/AI_NAVIGATION.md
docs/adr/0001-architecture-style.md
```

Cada modulo complexo deve ter:

```txt
README.md
PUBLIC_API.md
```

O `PUBLIC_API.md` responde:

- o que este modulo faz;
- quais use cases existem;
- quais contratos outros modulos podem importar;
- quais arquivos sao internos;
- quais tabelas/adaptadores usa.

Isso ajuda muito uma IA futura a nao sair abrindo tudo nem importar coisa
privada por engano.

## Definition of done da nova arquitetura

Um pacote so esta "limpo" quando:

- router tem no maximo HTTP/dependencias;
- use cases sao nomeados por acao de negocio;
- dominio nao importa infra;
- Supabase esta em adapter/repositorio;
- OpenAI esta em adapter;
- arquivos ficam abaixo do limite;
- funcoes criticas tem testes;
- imports publicos estao em `public.py` ou `ports.py`;
- erros de negocio sao explicitos;
- docs do modulo existem;
- lint, compile e testes passam.

## Resultado esperado

No final, o projeto deve parecer assim para uma pessoa ou IA:

- Quero registrar venda: abrir `modules/vendas/use_cases/registrar_venda.py`.
- Quero entender estoque: abrir `modules/vendas/domain/availability.py`.
- Quero entender preco vigente: abrir `modules/catalogo/domain/pricing.py`.
- Quero entender IA: abrir `modules/ia/domain/intent.py` e `modules/ia/use_cases`.
- Quero entender custos: abrir `modules/custos/domain/recipe_cost.py`.
- Quero mexer em Supabase: abrir `adapters/supabase_*.py`.
- Quero mexer em prompt: abrir `prompts/*.md`.

Esse e o ponto: cada pergunta tem um lugar obvio.
