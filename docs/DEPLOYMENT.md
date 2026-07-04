# Deploy da API

Este projeto esta pronto para subir como uma API FastAPI em um servico web Python.

## Opcao recomendada: Render

O arquivo `render.yaml` na raiz ja descreve o servico `padoka100-api`.

### 1. Antes de publicar

Confirme estes pontos:

- O SQL de `supabase/migrations/001_initial_schema.sql` ja foi aplicado no Supabase.
- O bucket `padoka-midia` existe no Supabase Storage.
- A branch com `render.yaml` foi enviada para o GitHub.
- Voce tem em maos as variaveis de ambiente do Supabase e da OpenAI.

### 2. Criar pelo Blueprint

No Render:

1. Va em `New > Blueprint`.
2. Conecte o repositorio `Boddenberg/padoka100`.
3. Escolha a branch que contem o arquivo `render.yaml`.
4. Confirme o Blueprint.
5. Preencha as variaveis marcadas como secretas.

### 3. Variaveis de ambiente

Configure no Render:

```text
APP_NAME=Padoka 100 API
APP_ENV=production
API_PREFIX=/api/v1
CORS_ORIGINS=https://seu-front.com
API_KEY=gere-uma-chave-grande-aqui

SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sua-service-role-key
SUPABASE_STORAGE_BUCKET=padoka-midia

OPENAI_API_KEY=sua-chave-openai
OPENAI_TEXT_MODEL=gpt-5.4-mini
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-transcribe
```

`API_KEY` e opcional localmente, mas deve ser configurada em producao. Quando ela existir, todos os endpoints em `/api/v1` exigem o header:

```text
X-API-Key: sua-chave
```

`/health`, `/docs`, `/redoc` e `/openapi.json` continuam acessiveis sem esse header para facilitar diagnostico.

### 4. Criar manualmente, sem Blueprint

Se preferir `New > Web Service`, use:

```text
Runtime: Python 3
Build Command: pip install --upgrade pip && pip install -e .
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health Check Path: /health
```

Tambem configure `PYTHON_VERSION=3.12`, ou deixe o Render ler o arquivo `.python-version`.

### 5. Teste depois do deploy

Troque `SUA_URL` pela URL gerada pelo Render:

```bash
curl https://SUA_URL/health
curl https://SUA_URL/api/v1/produtos -H "X-API-Key: sua-chave"
```

A documentacao interativa fica em:

```text
https://SUA_URL/docs
https://SUA_URL/redoc
```

### 6. Atualizar a collection do Insomnia

No environment `Local` ou em um novo environment de producao:

```text
base_url=https://SUA_URL
api_url=https://SUA_URL/api/v1
api_key=sua-chave
```

Para requests em `/api/v1`, adicione o header:

```text
X-API-Key: {{ _.api_key }}
```

## Observacoes de seguranca

- Nunca suba `.env` para o GitHub.
- Nunca coloque `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY` ou `API_KEY` direto em arquivos versionados.
- Use a `SUPABASE_SERVICE_ROLE_KEY` apenas no backend.
- Antes de liberar para uso real, revise CORS e autentificacao do app cliente.
