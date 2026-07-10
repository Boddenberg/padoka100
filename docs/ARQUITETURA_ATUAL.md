# Arquitetura atual (pos-refatoracao)

Este documento descreve o **estado real** do backend depois da rodada de
reestruturacao. Ele complementa o [PLANO_REARQUITETURA_MODERNA.md](PLANO_REARQUITETURA_MODERNA.md)
(que descreve a direcao) registrando o que ja esta implementado e o que falta.

## Como cada pergunta vira um lugar obvio

| Quero entender... | Abra |
| --- | --- |
| preco vigente de produto | `modules/produtos/domain/pricing.py` |
| disponibilidade / esgotamento de venda | `modules/vendas/domain/availability.py` |
| sobras do dia anterior | `modules/dias_de_venda/domain/sobras.py` |
| inicio / correcao de dia | `modules/dias_de_venda/use_cases/` |
| consolidacao de relatorios | `modules/relatorios/domain/agregacao.py` |
| comando de IA sem OpenAI (fallback) | `modules/ia/domain/fallback.py` |
| normalizacao de texto da IA | `modules/ia/domain/texto.py` |
| conversao de unidade / custo | `modules/custos/domain/unidades.py` |
| matching de ingrediente | `modules/custos/domain/ingredientes.py` |
| cliente Supabase / OpenAI | `infra/supabase/client.py`, `infra/openai/client.py` |
| checagem de API key | `core/security.py` |

## Camadas e regra de dependencia

```txt
api (router)  ->  servico (fachada / orquestracao)  ->  use_cases  ->  domain (puro)
                                     |                        |
                                     +------->  adapters / infra (Supabase, OpenAI, storage)
```

- **domain**: funcoes puras, sem rede. Nao importam FastAPI, Supabase nem OpenAI.
  Rodam nos testes sem mocks.
- **use_cases**: orquestram domain + repositorios para uma acao de negocio.
- **servico.py**: fachada fina; mantem a API publica que router e outros modulos
  ja consomem. Onde os fluxos grandes foram fatiados, o servico delega para
  `use_cases/` (via import deferido quando ha risco de ciclo).
- **adapters / infra**: todo acesso a Supabase/OpenAI/storage.

Um script de guarda-corpo verifica os limites:

```bash
python scripts/architecture_report.py            # relatorio
python scripts/architecture_report.py --fail      # falha se houver violacao
```

Limites: arquivo <= 500 linhas, funcao/classe <= 70 linhas, sem import cruzado
de `*.servico` entre modulos (preferir `public.py`).

## Estado por modulo

| Modulo | Estado | Observacao |
| --- | --- | --- |
| produtos | ✅ clean | use_cases + domain + adapters + public.py |
| vendas | ✅ clean | use_cases + domain + adapters |
| dias_de_venda | ✅ refatorado | domain/sobras, domain/regras_dia, use_cases (iniciar/corrigir) |
| relatorios | ✅ refatorado | domain/agregacao (consolidacao pura) |
| ia | 🟡 parcial | domain (acoes/vocabulario/texto/fallback) extraido; servico ainda orquestra OpenAI/confirmacao/execucao |
| custos | 🟡 parcial | domain (unidades/ingredientes/receita) extraido; servico ainda faz CRUD/compras/lista |
| custos.assistente | 🔴 pendente | `assistente_servico.py` (~2,7k linhas) ainda monolitico |
| admin.seed | 🔴 pendente | geracao fake acoplada a persistencia |
| notificacoes | 🟡 parcial | funciona; falta separar dominio/repositorio e enum de status |
| auth, locais, midia, historico, rag | ⚙️ estaveis | menores; padrao pode ser aplicado depois |

## Infra compartilhada

- `infra/supabase/client.py` — cliente Supabase (cache via `lru_cache`).
- `infra/openai/client.py` — cliente OpenAI.
- `infra/supabase/payload.py` — serializacao para o banco (`to_db_payload`, etc.).
- `infra/supabase/result.py` — helpers de resultado (`one_or_none`, `inserted_one`,
  `executar_lista_opcional`, ...).
- `app/db/*` e `app/shared/db.py` sao **reexports de compatibilidade** para a infra
  (nao adicionar logica nova neles; importar de `infra` em codigo novo).

## Testes

```bash
pip install -e ".[dev]"          # instala pytest e ruff
python -m pytest                 # suite de dominio puro
python -m ruff check .           # lint
python -m compileall -q app      # smoke de compilacao
```

Os testes cobrem o **dominio puro** extraido (preco, disponibilidade, sobras,
agregacao de relatorios, fallback/normalizacao da IA, unidades e matching de
custos) e a checagem de API key. Nao ha testes de integracao com Supabase/OpenAI.

## Proximos passos recomendados

1. Fatiar `custos/assistente_servico.py` em `assistant/` (session, draft,
   extraction, questions, simulation, confirmation) — maior item restante.
2. Terminar `ia`: extrair geracao de analise, montagem de confirmacao e execucao
   para `use_cases/` + `domain/`; tirar prompts/JSON de extracao do Python.
3. Terminar `custos`: mover CRUD/compras/lista para use_cases + repositorio.
4. `admin/seed`: separar factories deterministicas da persistencia; restringir a
   ambiente nao-producao.
5. Dedup final: migrar as copias de `_executar_lista_opcional`/`_erro_tabela_ausente`
   (ia, custos, notificacoes) para `infra/supabase/result.py`.
6. Seguranca (com cuidado, muda contrato): dependencias `Publico/UsuarioAtual/Admin`
   e protecao explicita de rotas sensiveis.
7. Cobertura de testes para os fluxos criticos restantes conforme cada fatia sair.
