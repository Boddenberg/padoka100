alter table public.usuarios
  add column if not exists supabase_auth_id uuid;

alter table public.usuarios
  alter column senha_hash drop not null;

create unique index if not exists usuarios_supabase_auth_id_unico_idx
  on public.usuarios (supabase_auth_id)
  where supabase_auth_id is not null;

