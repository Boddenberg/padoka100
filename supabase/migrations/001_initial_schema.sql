create extension if not exists pgcrypto;

create or replace function public.definir_atualizado_em()
returns trigger
language plpgsql
as $$
begin
  new.atualizado_em = now();
  return new;
end;
$$;

create table if not exists public.produtos (
  id uuid primary key default gen_random_uuid(),
  nome text not null,
  slug text,
  descricao text,
  descricao_visual text,
  url_imagem_principal text,
  cor_botao text,
  ordem_exibicao integer not null default 0,
  situacao text not null default 'ativo' check (situacao in ('ativo', 'inativo')),
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create unique index if not exists produtos_slug_unico_idx
  on public.produtos (slug)
  where slug is not null;

drop trigger if exists produtos_definir_atualizado_em on public.produtos;
create trigger produtos_definir_atualizado_em
before update on public.produtos
for each row execute function public.definir_atualizado_em();

create table if not exists public.versoes_preco_produto (
  id uuid primary key default gen_random_uuid(),
  produto_id uuid not null references public.produtos(id) on delete cascade,
  preco_venda numeric(12, 2) not null check (preco_venda >= 0),
  preco_custo numeric(12, 2) not null default 0 check (preco_custo >= 0),
  moeda text not null default 'BRL',
  vigente_desde date not null,
  vigente_ate date,
  motivo text,
  criado_em timestamptz not null default now(),
  check (vigente_ate is null or vigente_ate >= vigente_desde)
);

create unique index if not exists versoes_preco_produto_dia_unico_idx
  on public.versoes_preco_produto (produto_id, vigente_desde);

create index if not exists versoes_preco_produto_busca_idx
  on public.versoes_preco_produto (produto_id, vigente_desde desc, vigente_ate);

create table if not exists public.locais (
  id uuid primary key default gen_random_uuid(),
  nome text not null,
  endereco_texto text,
  descricao text,
  url_imagem_principal text,
  situacao text not null default 'ativo' check (situacao in ('ativo', 'inativo')),
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

drop trigger if exists locais_definir_atualizado_em on public.locais;
create trigger locais_definir_atualizado_em
before update on public.locais
for each row execute function public.definir_atualizado_em();

create table if not exists public.dias_de_venda (
  id uuid primary key default gen_random_uuid(),
  data_venda date not null,
  local_id uuid references public.locais(id) on delete set null,
  nome_local_no_momento text,
  observacoes text,
  situacao text not null default 'aberto' check (situacao in ('aberto', 'fechado')),
  aberto_em timestamptz not null default now(),
  fechado_em timestamptz,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create index if not exists dias_de_venda_data_idx
  on public.dias_de_venda (data_venda desc);

create index if not exists dias_de_venda_situacao_idx
  on public.dias_de_venda (situacao);

drop trigger if exists dias_de_venda_definir_atualizado_em on public.dias_de_venda;
create trigger dias_de_venda_definir_atualizado_em
before update on public.dias_de_venda
for each row execute function public.definir_atualizado_em();

create table if not exists public.itens_producao (
  id uuid primary key default gen_random_uuid(),
  dia_de_venda_id uuid not null references public.dias_de_venda(id) on delete cascade,
  produto_id uuid not null references public.produtos(id) on delete restrict,
  nome_produto_no_momento text not null,
  url_imagem_produto_no_momento text,
  versao_preco_id uuid references public.versoes_preco_produto(id) on delete set null,
  preco_venda_unitario_no_momento numeric(12, 2) not null check (preco_venda_unitario_no_momento >= 0),
  preco_custo_unitario_no_momento numeric(12, 2) not null default 0 check (preco_custo_unitario_no_momento >= 0),
  quantidade_produzida integer not null check (quantidade_produzida >= 0),
  observacoes text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  unique (dia_de_venda_id, produto_id)
);

create index if not exists itens_producao_dia_idx
  on public.itens_producao (dia_de_venda_id);

drop trigger if exists itens_producao_definir_atualizado_em on public.itens_producao;
create trigger itens_producao_definir_atualizado_em
before update on public.itens_producao
for each row execute function public.definir_atualizado_em();

create table if not exists public.interacoes_ia (
  id uuid primary key default gen_random_uuid(),
  dia_de_venda_id uuid references public.dias_de_venda(id) on delete set null,
  tipo_entrada text not null check (tipo_entrada in ('texto', 'audio')),
  texto_original text,
  url_audio text,
  acao_interpretada jsonb,
  dados_confirmacao jsonb,
  situacao text not null default 'interpretada' check (situacao in ('interpretada', 'confirmada', 'rejeitada', 'falhou')),
  mensagem_erro text,
  criado_em timestamptz not null default now()
);

create table if not exists public.vendas (
  id uuid primary key default gen_random_uuid(),
  dia_de_venda_id uuid not null references public.dias_de_venda(id) on delete cascade,
  tipo_entrada text not null default 'manual' check (tipo_entrada in ('manual', 'audio', 'ia')),
  interacao_ia_id uuid references public.interacoes_ia(id) on delete set null,
  texto_original text,
  url_audio text,
  observacoes text,
  situacao text not null default 'ativa' check (situacao in ('ativa', 'cancelada')),
  ocorrido_em timestamptz not null default now(),
  cancelado_em timestamptz,
  motivo_cancelamento text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create index if not exists vendas_dia_idx
  on public.vendas (dia_de_venda_id, ocorrido_em desc);

create index if not exists vendas_situacao_idx
  on public.vendas (situacao);

drop trigger if exists vendas_definir_atualizado_em on public.vendas;
create trigger vendas_definir_atualizado_em
before update on public.vendas
for each row execute function public.definir_atualizado_em();

create table if not exists public.itens_venda (
  id uuid primary key default gen_random_uuid(),
  venda_id uuid not null references public.vendas(id) on delete cascade,
  dia_de_venda_id uuid not null references public.dias_de_venda(id) on delete cascade,
  produto_id uuid not null references public.produtos(id) on delete restrict,
  nome_produto_no_momento text not null,
  url_imagem_produto_no_momento text,
  versao_preco_id uuid references public.versoes_preco_produto(id) on delete set null,
  preco_venda_unitario_no_momento numeric(12, 2) not null check (preco_venda_unitario_no_momento >= 0),
  preco_custo_unitario_no_momento numeric(12, 2) not null default 0 check (preco_custo_unitario_no_momento >= 0),
  quantidade integer not null check (quantidade > 0),
  valor_total_venda numeric(12, 2) not null check (valor_total_venda >= 0),
  valor_total_custo numeric(12, 2) not null default 0 check (valor_total_custo >= 0),
  criado_em timestamptz not null default now()
);

create index if not exists itens_venda_dia_idx
  on public.itens_venda (dia_de_venda_id);

create index if not exists itens_venda_produto_idx
  on public.itens_venda (produto_id);

create table if not exists public.midias (
  id uuid primary key default gen_random_uuid(),
  tipo_entidade text not null check (tipo_entidade in ('produto', 'local', 'dia_de_venda', 'venda', 'interacao_ia')),
  entidade_id uuid not null,
  bucket text not null,
  caminho_arquivo text not null,
  url_publica text,
  tipo_conteudo text,
  descricao text,
  texto_alternativo text,
  criado_em timestamptz not null default now()
);

create index if not exists midias_entidade_idx
  on public.midias (tipo_entidade, entidade_id, criado_em desc);

create table if not exists public.eventos_linha_do_tempo (
  id uuid primary key default gen_random_uuid(),
  dia_de_venda_id uuid references public.dias_de_venda(id) on delete set null,
  tipo_entidade text not null,
  entidade_id uuid,
  tipo_evento text not null,
  titulo text not null,
  detalhes jsonb not null default '{}'::jsonb,
  criado_em timestamptz not null default now()
);

create index if not exists eventos_linha_do_tempo_dia_idx
  on public.eventos_linha_do_tempo (dia_de_venda_id, criado_em desc);

create index if not exists eventos_linha_do_tempo_entidade_idx
  on public.eventos_linha_do_tempo (tipo_entidade, entidade_id, criado_em desc);

insert into storage.buckets (id, name, public)
values ('padoka-midia', 'padoka-midia', true)
on conflict (id) do nothing;
