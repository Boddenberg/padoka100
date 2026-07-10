# Padoka 100

Backend em Python/FastAPI para apoiar a rotina de uma pequena padaria familiar.

O sistema deve ser simples para quem vende no dia a dia e bem estruturado por
dentro para evoluir com seguranca. A API guarda catalogo, venda do dia,
historico, relatorios, midia, comandos por IA e bases futuras para perfil,
permissoes, analises e custos reais de produtos.

Este README e a referencia atual do produto e da arquitetura. Antes de criar
novas funcionalidades grandes, alinhe aqui o plano geral, as regras de negocio e
os contratos esperados.

## Tecnologias reais do projeto

- Linguagem: Python 3.12+
- Framework: FastAPI
- Banco de dados: Supabase Postgres
- Storage: Supabase Storage, bucket `padoka-midia`
- ORM/ODM: nenhum no momento; acesso via cliente oficial `supabase-py`
- Validacao/DTOs: Pydantic
- Autenticacao: sessao local com senha PBKDF2 + Bearer token, tokens do Supabase Auth
  (ver [docs/SUPABASE_AUTH.md](docs/SUPABASE_AUTH.md)) e API key opcional via `X-API-Key`
- Autorizacao: papeis (`usuario`/`administrador`/`dono`) + planos de acesso por
  capacidade (ver [docs/ACCESS_PLANS.md](docs/ACCESS_PLANS.md))
- IA: OpenAI API para interpretar comandos de texto/audio e, futuramente, analises
- Testes: `pytest` cobrindo o dominio puro (`python -m pytest`); `ruff` para lint
  (ver [docs/ARQUITETURA_ATUAL.md](docs/ARQUITETURA_ATUAL.md))
- Gerenciador/empacotamento: `pip`, `pyproject.toml`, Hatchling
- Ambiente: variaveis em `.env` via `pydantic-settings`
- Deploy: configuracoes para Render (`render.yaml`) e Railway (`railway.json`)

## Rodando localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
uvicorn app.main:app --reload
```

Depois de configurar as chaves no `.env`, aplique os SQLs de
`supabase/migrations` em ordem no projeto Supabase.

A documentacao interativa fica em:

- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

## Endpoints principais

- `GET /health`
- `GET /api/v1/produtos`
- `POST /api/v1/produtos`
- `GET /api/v1/produtos/{produto_id}`
- `PATCH /api/v1/produtos/{produto_id}`
- `GET /api/v1/produtos/{produto_id}/precos`
- `POST /api/v1/produtos/{produto_id}/precos`
- `POST /api/v1/produtos/{produto_id}/midia`
- `GET /api/v1/locais`
- `POST /api/v1/locais`
- `GET /api/v1/locais/{local_id}`
- `PATCH /api/v1/locais/{local_id}`
- `GET /api/v1/dias-de-venda`
- `POST /api/v1/dias-de-venda`
- `GET /api/v1/dias-de-venda/atual`
- `POST /api/v1/dias-de-venda/iniciar-hoje`
- `GET /api/v1/dias-de-venda/{dia_de_venda_id}`
- `PATCH /api/v1/dias-de-venda/{dia_de_venda_id}`
- `POST /api/v1/dias-de-venda/{dia_de_venda_id}/itens-producao`
- `POST /api/v1/dias-de-venda/{dia_de_venda_id}/fechar`
- `POST /api/v1/dias-de-venda/{dia_de_venda_id}/correcoes`
- `POST /api/v1/vendas`
- `GET /api/v1/vendas/por-dia/{dia_de_venda_id}`
- `GET /api/v1/vendas/{venda_id}`
- `POST /api/v1/vendas/{venda_id}/cancelar`
- `GET /api/v1/relatorios/dias/{dia_de_venda_id}/resumo`
- `GET /api/v1/relatorios/dias/por-data/{data_venda}/resumo`
- `GET /api/v1/relatorios/dias/{dia_de_venda_id}/produtos-venda`
- `GET /api/v1/relatorios/periodo`
- `GET /api/v1/relatorios/periodo/resumo`
- `GET /api/v1/historico/linha-do-tempo`
- `POST /api/v1/midia/{tipo_entidade}/{entidade_id}`
- `POST /api/v1/ia/interpretar-comando`
- `POST /api/v1/ia/transcrever-audio`
- `POST /api/v1/ia/interacoes/{interacao_ia_id}/confirmar`
- `POST /api/v1/ia/interpretar-comando-de-venda`
- `POST /api/v1/ia/transcrever-audio-de-venda`
- `POST /api/v1/ia/interacoes/{interacao_ia_id}/confirmar-venda`
- `GET /api/v1/ia/dados-estruturados/periodo`
- `POST /api/v1/ia/analises/padrao`
- `POST /api/v1/ia/analises/especifica`
- `POST /api/v1/auth/registrar`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/trocar-senha`
- `GET /api/v1/auth/usuarios`
- `PATCH /api/v1/auth/usuarios/{usuario_id}/papel`
- `GET /api/v1/perfil/me`
- `PATCH /api/v1/perfil/me`
- `POST /api/v1/perfil/me/foto`
- `GET /api/v1/custos/insumos`
- `POST /api/v1/custos/insumos`
- `PATCH /api/v1/custos/insumos/{insumo_id}`
- `GET /api/v1/custos/produtos-com-receita`
- `GET /api/v1/custos/produtos/{produto_id}/receitas`
- `POST /api/v1/custos/produtos/{produto_id}/receitas`
- `POST /api/v1/custos/produtos/{produto_id}/custos-adicionais`
- `GET /api/v1/custos/produtos/{produto_id}/calculo`
- `POST /api/v1/custos/assistente/sessoes`
- `GET /api/v1/custos/assistente/sessoes/{sessao_id}`
- `POST /api/v1/custos/assistente/sessoes/{sessao_id}/entradas/texto`
- `POST /api/v1/custos/assistente/sessoes/{sessao_id}/entradas/formulario`
- `POST /api/v1/custos/assistente/sessoes/{sessao_id}/entradas/arquivo`
- `PATCH /api/v1/custos/assistente/sessoes/{sessao_id}/rascunho`
- `POST /api/v1/custos/assistente/sessoes/{sessao_id}/confirmar`
- `POST /api/v1/custos/assistente/sessoes/{sessao_id}/descartar`
- `GET /api/v1/notificacoes`
- `GET /api/v1/notificacoes/nao-lidas/contagem`
- `POST /api/v1/notificacoes/{notificacao_id}/lida`
- `POST /api/v1/notificacoes/{notificacao_id}/ler`
- `POST /api/v1/notificacoes/{notificacao_id}/nao-lida`
- `POST /api/v1/notificacoes/{notificacao_id}/ocultar`

Exemplos de uso ficam em `docs/API_USAGE.md`.

Autenticacao atual: nenhum endpoint exige Bearer token. O login ainda devolve
`access_token` por compatibilidade, mas o front pode chamar todas as rotas sem
enviar `Authorization`.

## Regras de negocio centrais

### Catalogo e venda do dia

O catalogo contem todos os produtos cadastrados.

A venda do dia deve mostrar somente produtos que participaram daquele dia:

- entrou na venda do dia: aparece;
- entrou e esgotou: continua aparecendo como esgotado;
- nunca entrou no dia: nao aparece na aba de venda.

### Historico e snapshots

Preco e historico nao devem ser reescritos sem rastro.

Quando o preco de um produto muda, o backend cria uma nova versao de preco.
Vendas e producoes salvam snapshots do nome, imagem e preco daquele dia. Assim,
se o pao de calabresa custava R$ 8,00 na segunda e mudou para R$ 10,00 na
quinta, a segunda continua mostrando R$ 8,00 para sempre.

### Dia fechado e correcao retroativa

Dia fechado pode ser corrigido, mas nao deve ser simplesmente reaberto sem
controle. Correcoes de dias fechados precisam preservar:

- dado original;
- dado corrigido;
- usuario que corrigiu, quando existir autenticacao;
- data da correcao;
- motivo opcional;
- alteracoes em formato estruturado.

### Datas futuras

Consultas, resumos e analises nao devem aceitar periodo futuro. Mesmo que o
front bloqueie visualmente, a API deve validar a data final no backend.

## Estado atual

Ja existe:

- estrutura FastAPI com `app.main:app`, CORS, healthcheck e configuracao por `.env`;
- modulos em portugues dentro de `app/modules`;
- integracao com Supabase e OpenAI;
- migrations SQL para schema inicial, sobras, correcoes, auth/perfil, custos,
  midia de usuario e custeio assistido;
- cadastro, listagem, atualizacao e consulta de produtos;
- historico de precos por versao;
- cadastro e atualizacao de locais;
- abertura, edicao, consulta e fechamento de dias de venda;
- virada de dia com decisao explicita sobre sobras;
- registro de producao com snapshot de produto, imagem e preco;
- registro de vendas manuais com snapshots de nome, imagem, preco e custo;
- cancelamento de venda sem apagar historico;
- correcao retroativa de dias fechados;
- relatorios por dia, data e periodo;
- consulta de produtos que participaram da venda do dia;
- bloqueio de datas futuras em consultas sensiveis;
- historico estruturado para o front;
- upload de midia;
- interpretacao de comandos por texto/audio com confirmacao antes de salvar;
- autenticacao real com senha hash PBKDF2, bearer token e logout;
- perfil do usuario com foto, upload de foto, nome, nascimento, telefone e e-mail;
- papeis `usuario`, `administrador` e `dono` em rotas novas sensiveis;
- dados estruturados para IA por periodo;
- analise padrao e especifica com secoes estruturadas e resumo local quando OpenAI nao estiver configurada;
- modulo inicial de custos com insumos, receitas, custos adicionais e calculo por produto;
- assistente de custeio com sessoes, rascunho revisavel, entrada por texto,
  formulario, audio e imagem/print, simulacao de custo, perguntas pendentes,
  confirmacao final e atualizacao do custo vigente do produto;
- login com token do Supabase Auth e sincronizacao do perfil local;
- planos de acesso (`basico`, `analitico`, `ia`, `admin`) com capacidades por rota;
- suite de testes de dominio puro com pytest (144 casos) e lint com ruff.

Ainda nao existe como funcionalidade completa:

- integracao fiscal oficial por XML/chave de acesso de nota;
- testes automatizados de integracao.

## Autenticacao e perfil

Implementado. O backend aceita tres formas de credencial durante a transicao:

- **Sessao local**: cadastro/login com e-mail e senha (hash PBKDF2), Bearer token
  proprio, logout, troca de senha e expiracao de sessao.
- **Supabase Auth**: Bearer token emitido pelo Supabase e validado em
  `/auth/v1/user`; o perfil local em `public.usuarios` e criado/sincronizado
  automaticamente (ver [docs/SUPABASE_AUTH.md](docs/SUPABASE_AUTH.md)).
- **API key** (`X-API-Key`): compatibilidade operacional para scripts.

O perfil guarda foto, nome, data de nascimento, telefone e e-mail, com upload de
foto via Supabase Storage.

## Permissoes e planos de acesso

Implementado em duas camadas (ver [docs/ACCESS_PLANS.md](docs/ACCESS_PLANS.md)):

- **Papeis**: `usuario`, `administrador`, `dono` — rotas administrativas exigem
  admin real (`exigir_admin_real`).
- **Planos por capacidade**: `basico`, `analitico`, `ia` e `admin` liberam
  conjuntos crescentes de capacidades (ex.: `vendas.operar`,
  `relatorios.avancados`, `ia.analitica`, `custos.assistente`). Cada rota declara
  a capacidade de que precisa via `exigir_capacidade("...")`; o mapa puro vive em
  `app/modules/auth/domain/capacidades.py`.

## Dados estruturados para IA

A IA nao deve receber dados crus e baguncados do banco. O backend deve montar
estruturas por:

- dia;
- semana;
- mes;
- periodo personalizado;
- produto;
- categoria, se existir futuramente.

Resumo diario conceitual:

```json
{
  "data": "2026-07-08",
  "faturamentoTotal": 650,
  "quantidadeTotalProduzida": 46,
  "quantidadeTotalVendida": 25,
  "quantidadeTotalSobrando": 21,
  "produtos": [
    {
      "produto": "Pao de Queijo",
      "quantidadeProduzida": 20,
      "quantidadeVendida": 20,
      "quantidadeSobrando": 0,
      "faturamento": 300
    }
  ]
}
```

Resumo por periodo conceitual:

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
      "produto": "Pao de Queijo",
      "totalProduzido": 100,
      "totalVendido": 90,
      "totalSobrando": 10,
      "faturamento": 1350
    }
  ]
}
```

Essas estruturas devem indicar se houve correcoes retroativas, produtos
esgotados, sobras altas, dias sem venda e dados incompletos.

## Analises com IA

### Analise padrao

O front seleciona um periodo, como julho, e pede uma analise geral. O backend
deve montar os dados estruturados do periodo e enviar para a IA responder com
base nos fatos salvos.

A analise padrao deve considerar:

- faturamento;
- produtos vendidos;
- produtos produzidos;
- sobras;
- produtos esgotados;
- comparacao entre dias;
- historico de vendas;
- correcoes retroativas relevantes.

### Analise especifica

Alem da analise padrao, o backend deve aceitar pedidos especificos do usuario,
como:

- analise somente abril;
- ignore os pudins;
- veja so o pao de calabresa;
- compare pao de queijo com pao sovado;
- diga o que mais sobrou;
- diga o que deveria ser produzido menos.

O backend deve receber periodo, contexto opcional, dados estruturados e filtros
solicitados. A IA deve responder somente com base nesses dados e deixar claro
quando algo nao estiver disponivel.

## Custos reais dos produtos

O calculo de custo dos produtos sera uma das partes mais complexas do projeto.
O sistema precisa permitir que o dono informe dados aos poucos, com status de
confianca.

Informacoes que o backend deve conseguir guardar:

- insumos comprados;
- preco dos insumos;
- quantidade comprada;
- unidade de medida;
- receita do produto;
- quantidade usada na receita;
- rendimento da receita;
- custos indiretos;
- embalagem;
- transporte;
- status de confirmacao das informacoes.

Exemplo de insumo:

```json
{
  "nome": "Farinha de trigo",
  "quantidadeComprada": 1,
  "unidadeCompra": "kg",
  "precoTotal": 5.0,
  "custoPorUnidade": 5.0
}
```

Exemplo de receita:

```json
{
  "produto": "Pao Sovado",
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

Exemplo de custo calculado:

```json
{
  "produto": "Pao Sovado",
  "custoTotalReceita": 28.5,
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

Status possiveis para dados de custo:

- `CONFIRMADO`
- `ESTIMADO`
- `PENDENTE`
- `PRECISA_REVISAR`

Custos que devem poder entrar no calculo:

- ingredientes principais: farinha, leite, ovos, queijo, calabresa, presunto,
  frango, acucar, manteiga, oleo e fermento;
- ingredientes pequenos: sal, temperos, oregano, alho, cebola e essencia;
- custos indiretos: gas, energia eletrica, agua, tempo de forno,
  geladeira/freezer e desgaste de equipamento futuramente;
- embalagem: saquinho, bandeja, etiqueta, caixa, papel e plastico filme;
- transporte: gasolina, estacionamento, frete e taxa de entrega.

A IA pode ajudar a montar custos, mas nao pode inventar dados:

- se nao souber, pergunta;
- se for estimativa, marca como estimativa;
- se for confirmado pelo usuario, marca como confirmado;
- antes de salvar, sempre pede confirmacao.

Entradas podem vir por texto, audio, imagem/print, formulario ou correcao
posterior via assistente de custeio. Foto ruim ou leitura insegura deve gerar
pedido de confirmacao manual antes de salvar.

## Arquitetura — como era e como ficou

O projeto passou por uma reestruturacao profunda em julho/2026, guiada pelo
[PLANO_REARQUITETURA_MODERNA.md](docs/PLANO_REARQUITETURA_MODERNA.md) e
registrada em [ARQUITETURA_ATUAL.md](docs/ARQUITETURA_ATUAL.md). O objetivo foi
manter o comportamento externo intacto (endpoints, contratos, schemas, env vars)
e reorganizar o interior para leitura, teste e manutencao.

### Como era

```txt
app/
  api/router.py
  core/            # config, errors
  db/              # clients Supabase/OpenAI
  modules/
    <modulo>/
      router.py    # rotas finas (ok)
      servico.py   # TUDO: regra de negocio + queries Supabase +
                   # chamadas OpenAI + prompts + formatacao de resposta
      esquemas.py
  shared/          # helpers soltos (datas, db, slugs...)
```

Sintomas medidos antes da reestruturacao:

| Problema | Medida |
| --- | --- |
| 4 arquivos concentravam 54% do codigo | `assistente_servico.py` 2.686 linhas, `ia/servico.py` 2.262, `custos/servico.py` 1.632, `dias_de_venda/servico.py` 1.052 |
| Funcoes gigantes | 22 funcoes acima de 70 linhas (maior: 209) |
| Testes automatizados | **zero** |
| Acoplamento entre modulos | 18 imports diretos de `servico` de outros modulos |
| Infra duplicada | `app/db/*`, `app/shared/db.py` e helpers copiados 4x (`_erro_tabela_ausente`) |
| Prompts de IA | strings e JSON schemas embutidos no meio dos servicos |
| Seguranca de borda | lista de rotas isentas hardcoded no `main.py` |

### Como ficou

```txt
app/
  main.py               # so monta o app; regra de API key em core/security.py
  api/router.py
  core/                 # config, errors, clock (fonte unica de tempo), security
  infra/                # DETALHE TECNICO isolado
    supabase/           #   client, payload (serializacao), result (one_or_none,
    openai/             #   executar_lista_opcional, tabela/coluna ausente...)
  db/, shared/db.py     # reexports de compatibilidade para infra (nao crescem)
  modules/
    <modulo>/
      router.py         # HTTP + dependencias de auth/capacidade
      esquemas.py       # DTOs Pydantic
      servico.py        # FACHADA fina: delega para use_cases/domain
      use_cases/        # 1 acao de negocio por arquivo (criar_produto, ...)
      domain/           # regra PURA: roda sem rede, sem mocks
      adapters/         # unico lugar que fala com Supabase/OpenAI/HTTP
      prompts/          # prompts e JSON schemas de IA em arquivos proprios
      public.py         # contrato para outros modulos (sem tocar internals)
tests/
  unit/<modulo>/        # pytest cobrindo o dominio puro (144 casos)
scripts/
  architecture_report.py  # guarda-corpo: arquivo <=500 linhas, funcao <=70,
                          # sem import cruzado de servico entre modulos
```

Fluxo de dependencia (imposto por convencao + relatorio):

```txt
router -> servico (fachada) -> use_cases -> domain (puro)
                    |               |
                    +---------> adapters/infra (Supabase, OpenAI, storage)
```

- `domain/` nunca importa FastAPI, Supabase ou OpenAI.
- IA interpreta e monta intencao; a execucao real passa por caso de uso de negocio.
- Modulos conversam via `public.py`, nao via helpers privados.

### Antes e depois em numeros

| Indicador | Antes | Depois |
| --- | --- | --- |
| Maior arquivo | 2.686 linhas | 1.970 (fatiamento em andamento) |
| `ia/servico.py` | 2.262 | 1.529 |
| `dias_de_venda/servico.py` | 1.052 | fachada + `domain/` + `use_cases/` |
| Funcao mais longa | 209 linhas | < 70 nos modulos tocados (exceto schema JSON de prompt) |
| Testes | 0 | 144 (dominio puro, sem mocks de rede) |
| Copias de helpers Supabase | 4 | 1 (em `infra/supabase/result.py`) |
| Prompts embutidos em servico | sim | arquivos proprios em `prompts/` |

### O que NAO mudou (de proposito)

- Endpoints, verbos, paths e response models — contrato HTTP identico.
- Migrations SQL e schema do banco (novas migrations so por feature).
- Variaveis de ambiente e deploy (Render/Railway).
- Textos de prompts de IA (apenas mudaram de arquivo).
- Comportamento de negocio: as fachadas `servico.py` mantem as mesmas
  assinaturas; a mudanca foi de organizacao, nao de regra.

### Validando localmente

```bash
pip install -e ".[dev]"
python -m pytest                        # 144 testes de dominio
python -m ruff check .                  # lint
python -m compileall -q app             # smoke de compilacao
python scripts/architecture_report.py   # limites de tamanho/acoplamento
```

Ao criar modulos novos, siga o padrao acima: rota fina, caso de uso nomeado por
acao de negocio, regra pura em `domain/`, Supabase/OpenAI atras de adapter e
contrato externo em `public.py`. Endpoints novos continuam documentados em
`docs/API_USAGE.md`.

## Panorama futuro

O backend deve evoluir para uma base simples de apoio a decisao. No futuro, o
sistema deve ajudar a responder:

- quanto vendemos hoje?
- quanto vendemos no mes?
- o que mais vende?
- o que mais sobra?
- o que devemos produzir menos?
- o que devemos produzir mais?
- qual produto da mais lucro?
- qual produto custa mais caro para produzir?
- existe padrao por dia da semana?
- a producao esta acima ou abaixo do ideal?

## Proximos passos recomendados

1. Terminar o fatiamento do assistente de custeio (perguntas, simulacao e
   confirmacao ainda vivem em `assistente_servico.py`).
2. Extrair a execucao de comandos confirmados da IA para casos de uso reais
   de venda/dia (`_executar_operacao_confirmada`).
3. Mover CRUD/compras/lista de `custos/servico.py` para use_cases + repositorio.
4. Separar persistencia da geracao no seed e restringir a ambiente nao-producao.
5. Testes de integracao com Supabase/OpenAI (hoje a suite cobre so dominio puro).
6. Integracao fiscal oficial por XML/chave de acesso de nota.

O detalhe do que falta por modulo fica em
[docs/ARQUITETURA_ATUAL.md](docs/ARQUITETURA_ATUAL.md).
7. Aplicar as migrations no Supabase real e testar ponta a ponta.
