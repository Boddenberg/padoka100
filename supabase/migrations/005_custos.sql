create table if not exists public.insumos (
  id uuid primary key default gen_random_uuid(),
  nome text not null,
  categoria text,
  quantidade_comprada numeric(14, 4) not null check (quantidade_comprada > 0),
  unidade_compra text not null,
  preco_total numeric(14, 2) not null check (preco_total >= 0),
  custo_por_unidade numeric(14, 6) not null check (custo_por_unidade >= 0),
  status text not null default 'CONFIRMADO'
    check (status in ('CONFIRMADO', 'ESTIMADO', 'PENDENTE', 'PRECISA_REVISAR')),
  observacoes text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create index if not exists insumos_nome_idx
  on public.insumos (nome);

drop trigger if exists insumos_definir_atualizado_em on public.insumos;
create trigger insumos_definir_atualizado_em
before update on public.insumos
for each row execute function public.definir_atualizado_em();

create table if not exists public.receitas_produto (
  id uuid primary key default gen_random_uuid(),
  produto_id uuid not null references public.produtos(id) on delete cascade,
  nome text,
  rendimento numeric(14, 4) not null check (rendimento > 0),
  unidade_rendimento text not null default 'unidade',
  status text not null default 'PENDENTE'
    check (status in ('CONFIRMADO', 'ESTIMADO', 'PENDENTE', 'PRECISA_REVISAR')),
  observacoes text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create index if not exists receitas_produto_produto_idx
  on public.receitas_produto (produto_id, criado_em desc);

drop trigger if exists receitas_produto_definir_atualizado_em on public.receitas_produto;
create trigger receitas_produto_definir_atualizado_em
before update on public.receitas_produto
for each row execute function public.definir_atualizado_em();

create table if not exists public.ingredientes_receita (
  id uuid primary key default gen_random_uuid(),
  receita_id uuid not null references public.receitas_produto(id) on delete cascade,
  insumo_id uuid references public.insumos(id) on delete set null,
  nome_insumo_no_momento text not null,
  quantidade_usada numeric(14, 4) not null check (quantidade_usada > 0),
  unidade text not null,
  custo_unitario_no_momento numeric(14, 6),
  custo_total_estimado numeric(14, 2),
  status text not null default 'PENDENTE'
    check (status in ('CONFIRMADO', 'ESTIMADO', 'PENDENTE', 'PRECISA_REVISAR')),
  observacoes text,
  criado_em timestamptz not null default now()
);

create index if not exists ingredientes_receita_receita_idx
  on public.ingredientes_receita (receita_id);

create table if not exists public.custos_adicionais_produto (
  id uuid primary key default gen_random_uuid(),
  produto_id uuid not null references public.produtos(id) on delete cascade,
  receita_id uuid references public.receitas_produto(id) on delete cascade,
  tipo text not null check (tipo in ('embalagem', 'transporte', 'indireto', 'outro')),
  nome text not null,
  valor numeric(14, 2) not null check (valor >= 0),
  status text not null default 'CONFIRMADO'
    check (status in ('CONFIRMADO', 'ESTIMADO', 'PENDENTE', 'PRECISA_REVISAR')),
  observacoes text,
  criado_em timestamptz not null default now()
);

create index if not exists custos_adicionais_produto_idx
  on public.custos_adicionais_produto (produto_id, criado_em desc);
