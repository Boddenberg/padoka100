# Supabase Auth no backend

O backend aceita dois formatos de autenticacao durante a transicao:

- `Authorization: Bearer <supabase_access_token>`: caminho principal para o app.
- `X-API-Key`: compatibilidade operacional para scripts/Insomnia quando `API_KEY` estiver configurada.

Quando recebe um Bearer token que nao pertence a uma sessao local antiga, a API valida o token no Supabase Auth em `/auth/v1/user`. Se o token for valido, o backend cria ou atualiza o perfil local em `public.usuarios` e aplica os mesmos papeis da aplicacao (`usuario`, `administrador`, `dono`).

## Migration obrigatoria

Aplique `supabase/migrations/012_supabase_auth_profiles.sql` depois das migrations anteriores. Ela adiciona:

- `usuarios.supabase_auth_id`, vinculado ao `auth.users.id`;
- `senha_hash` opcional, porque usuarios gerenciados pelo Supabase nao usam senha local;
- indice unico parcial para `supabase_auth_id`.

## Variaveis

O backend precisa das variaveis ja usadas pela integracao Supabase:

```text
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_KEY=sua-anon-key
SUPABASE_SERVICE_ROLE_KEY=sua-service-role-key
```

`SUPABASE_SERVICE_ROLE_KEY` continua apenas no backend. O app mobile usa somente a anon key publica.

