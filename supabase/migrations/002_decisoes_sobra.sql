create table if not exists public.decisoes_sobra (
  id uuid primary key default gen_random_uuid(),
  dia_origem_id uuid not null references public.dias_de_venda(id) on delete cascade,
  dia_destino_id uuid not null references public.dias_de_venda(id) on delete cascade,
  produto_id uuid not null references public.produtos(id) on delete restrict,
  nome_produto_no_momento text not null,
  url_imagem_produto_no_momento text,
  quantidade_sobra_origem integer not null check (quantidade_sobra_origem > 0),
  quantidade_usada_hoje integer not null check (quantidade_usada_hoje >= 0),
  quantidade_nao_usada_hoje integer not null check (quantidade_nao_usada_hoje >= 0),
  observacoes text,
  criado_em timestamptz not null default now(),
  check (quantidade_usada_hoje + quantidade_nao_usada_hoje = quantidade_sobra_origem),
  unique (dia_origem_id, dia_destino_id, produto_id)
);

create index if not exists decisoes_sobra_origem_idx
  on public.decisoes_sobra (dia_origem_id);

create index if not exists decisoes_sobra_destino_idx
  on public.decisoes_sobra (dia_destino_id);
