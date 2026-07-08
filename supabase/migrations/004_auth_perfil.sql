create table if not exists public.usuarios (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  senha_hash text not null,
  nome text,
  foto_url text,
  data_nascimento date,
  telefone text,
  papel text not null default 'usuario' check (papel in ('usuario', 'administrador', 'dono')),
  situacao text not null default 'ativo' check (situacao in ('ativo', 'inativo')),
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create unique index if not exists usuarios_email_unico_idx
  on public.usuarios (lower(email));

create index if not exists usuarios_papel_idx
  on public.usuarios (papel);

drop trigger if exists usuarios_definir_atualizado_em on public.usuarios;
create trigger usuarios_definir_atualizado_em
before update on public.usuarios
for each row execute function public.definir_atualizado_em();

create table if not exists public.sessoes_usuario (
  id uuid primary key default gen_random_uuid(),
  usuario_id uuid not null references public.usuarios(id) on delete cascade,
  token_hash text not null unique,
  expira_em timestamptz not null,
  revogado_em timestamptz,
  ultimo_uso_em timestamptz,
  criado_em timestamptz not null default now()
);

create index if not exists sessoes_usuario_usuario_idx
  on public.sessoes_usuario (usuario_id, criado_em desc);

create index if not exists sessoes_usuario_token_idx
  on public.sessoes_usuario (token_hash)
  where revogado_em is null;
