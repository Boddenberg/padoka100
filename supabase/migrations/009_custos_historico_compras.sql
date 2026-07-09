alter table public.insumos
  add column if not exists nome_normalizado text;

alter table public.insumos
  add column if not exists ultima_compra_em date;

create index if not exists insumos_nome_normalizado_idx
  on public.insumos (nome_normalizado);

create table if not exists public.insumos_precos (
  id uuid primary key default gen_random_uuid(),
  insumo_id uuid not null references public.insumos(id) on delete cascade,
  quantidade_comprada numeric(14, 4) not null check (quantidade_comprada > 0),
  unidade_compra text not null,
  preco_total numeric(14, 2) not null check (preco_total >= 0),
  custo_por_unidade numeric(14, 6) not null check (custo_por_unidade >= 0),
  vigente_desde date not null default current_date,
  origem text not null default 'manual'
    check (origem in ('manual', 'nota', 'assistente', 'importacao')),
  fornecedor text,
  fonte text,
  observacoes text,
  criado_em timestamptz not null default now()
);

create index if not exists insumos_precos_insumo_vigencia_idx
  on public.insumos_precos (insumo_id, vigente_desde desc, criado_em desc);

insert into public.insumos_precos (
  insumo_id,
  quantidade_comprada,
  unidade_compra,
  preco_total,
  custo_por_unidade,
  vigente_desde,
  origem,
  observacoes,
  criado_em
)
select
  insumos.id,
  insumos.quantidade_comprada,
  insumos.unidade_compra,
  insumos.preco_total,
  insumos.custo_por_unidade,
  coalesce(insumos.ultima_compra_em, insumos.criado_em::date, current_date),
  'importacao',
  insumos.observacoes,
  insumos.criado_em
from public.insumos
where not exists (
  select 1
  from public.insumos_precos precos
  where precos.insumo_id = insumos.id
);

update public.insumos
set ultima_compra_em = coalesce(ultima_compra_em, criado_em::date, current_date)
where ultima_compra_em is null;

create table if not exists public.listas_compras (
  id uuid primary key default gen_random_uuid(),
  nome text,
  data_referencia date not null default current_date,
  margem_percentual numeric(8, 4) not null default 0 check (margem_percentual >= 0),
  parametros jsonb not null default '{}'::jsonb,
  itens jsonb not null default '[]'::jsonb check (jsonb_typeof(itens) = 'array'),
  total_estimado numeric(14, 2),
  pendencias jsonb not null default '[]'::jsonb check (jsonb_typeof(pendencias) = 'array'),
  criado_em timestamptz not null default now()
);

create index if not exists listas_compras_criado_em_idx
  on public.listas_compras (criado_em desc);
