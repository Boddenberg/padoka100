create table if not exists public.correcoes_dia_fechado (
  id uuid primary key default gen_random_uuid(),
  dia_de_venda_id uuid not null references public.dias_de_venda(id) on delete cascade,
  usuario_id text,
  motivo text,
  alteracoes jsonb not null default '[]'::jsonb,
  criado_em timestamptz not null default now()
);

create index if not exists correcoes_dia_fechado_dia_idx
  on public.correcoes_dia_fechado (dia_de_venda_id, criado_em desc);
