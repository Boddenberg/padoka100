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

Depois de configurar as chaves no `.env`, aplique o SQL em `supabase/migrations/001_initial_schema.sql` no projeto Supabase.

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
- Tabelas principais em portugues: `produtos`, `versoes_preco_produto`, `locais`, `dias_de_venda`, `itens_producao`, `vendas`, `itens_venda`, `midias`, `interacoes_ia` e `eventos_linha_do_tempo`.
- Cadastro, listagem, atualizacao e consulta de produtos.
- Produtos preparados para uso visual com descricao, descricao visual, cor de botao, ordem de exibicao e imagem principal.
- Historico de precos por versao, com vigencia por data e sem sobrescrever o passado.
- Cadastro e atualizacao de locais/condominios.
- Abertura, edicao, consulta e fechamento de dias de venda.
- Registro de producao do dia com snapshot de produto, imagem e preco vigente.
- Registro de vendas manuais com snapshots de nome, imagem, preco de venda e custo.
- Cancelamento de venda sem apagar historico.
- Relatorios por dia e por periodo com produzido, vendido, sobra, faturamento bruto, custo estimado e lucro estimado.
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
