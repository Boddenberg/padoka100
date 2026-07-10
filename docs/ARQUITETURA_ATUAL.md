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
| analise local de periodo (sem OpenAI) | `modules/ia/domain/analise.py` |
| conversao de unidade / custo | `modules/custos/domain/unidades.py` |
| matching de ingrediente (insumos) | `modules/custos/domain/ingredientes.py` |
| rascunho do assistente de custeio | `modules/custos/assistant/rascunho.py` |
| coercoes de valores vindos da IA | `modules/custos/assistant/valores.py` |
| regras de ingrediente do assistente | `modules/custos/assistant/ingredientes.py` |
| prompt/schema de extracao de custeio | `modules/custos/prompts/extracao_custeio.py` |
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
| ia | 🟡 parcial | domain (acoes/vocabulario/texto/fallback/analise) extraido; servico ainda orquestra OpenAI/confirmacao/execucao |
| custos | 🟡 parcial | domain (unidades/ingredientes/receita) extraido; servico ainda faz CRUD/compras/lista |
| custos.assistente | 🟡 parcial | nucleo puro em `assistant/` (valores/ingredientes/rascunho) + prompts extraidos; servico (~2k linhas) ainda orquestra sessao/simulacao/confirmacao |
| admin.seed | 🟡 parcial | lote decomposto em passos por dia (rng estavel); persistencia ainda no mesmo arquivo |
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
agregacao de relatorios, fallback/normalizacao/analise da IA, unidades e
matching de custos, valores/ingredientes/rascunho do assistente) e a checagem
de API key. Nao ha testes de integracao com Supabase/OpenAI.

## Proximos passos recomendados

1. Terminar o assistente de custeio: extrair perguntas/pendencias, simulacao e
   confirmacao de `assistente_servico.py` (exigem injetar a busca de insumo,
   hoje acoplada ao Supabase).
2. Terminar `ia`: extrair montagem de confirmacao e `_executar_operacao_confirmada`
   para `use_cases/`; a execucao deve chamar os use cases reais de venda/dia.
3. Terminar `custos`: mover CRUD/compras/lista para use_cases + repositorio.
4. `admin/seed`: separar persistencia da geracao; restringir a ambiente
   nao-producao; teste de determinismo do lote (mesma seed => mesmas contagens).
5. Seguranca (com cuidado, muda contrato): dependencias `Publico/UsuarioAtual/Admin`
   e protecao explicita de rotas sensiveis.
6. Cobertura de testes para os fluxos criticos restantes conforme cada fatia sair.
