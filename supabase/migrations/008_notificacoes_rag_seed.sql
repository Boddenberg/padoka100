create extension if not exists vector;

create table if not exists public.notificacoes (
  id uuid primary key default gen_random_uuid(),
  titulo text not null,
  corpo text not null,
  publico text not null default 'todos' check (publico in ('todos', 'admins')),
  prioridade text not null default 'normal' check (prioridade in ('baixa', 'normal', 'alta')),
  status text not null default 'rascunho' check (status in ('rascunho', 'publicada', 'arquivada')),
  midias jsonb not null default '[]'::jsonb check (jsonb_typeof(midias) = 'array'),
  metadados jsonb not null default '{}'::jsonb,
  criado_por_usuario_id uuid references public.usuarios(id) on delete set null,
  publicado_em timestamptz,
  expira_em timestamptz,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  check (expira_em is null or publicado_em is null or expira_em > publicado_em)
);

create index if not exists notificacoes_publicas_idx
  on public.notificacoes (status, publico, publicado_em desc);

create index if not exists notificacoes_criado_em_idx
  on public.notificacoes (criado_em desc);

drop trigger if exists notificacoes_definir_atualizado_em on public.notificacoes;
create trigger notificacoes_definir_atualizado_em
before update on public.notificacoes
for each row execute function public.definir_atualizado_em();

create table if not exists public.notificacao_visualizacoes (
  id uuid primary key default gen_random_uuid(),
  notificacao_id uuid not null references public.notificacoes(id) on delete cascade,
  usuario_id uuid references public.usuarios(id) on delete cascade,
  visualizado_em timestamptz not null default now(),
  unique (notificacao_id, usuario_id)
);

create index if not exists notificacao_visualizacoes_notificacao_idx
  on public.notificacao_visualizacoes (notificacao_id, visualizado_em desc);

alter table public.midias
  drop constraint if exists midias_tipo_entidade_check;

alter table public.midias
  add constraint midias_tipo_entidade_check
  check (
    tipo_entidade in (
      'produto',
      'local',
      'dia_de_venda',
      'venda',
      'interacao_ia',
      'usuario',
      'sessao_custeio',
      'notificacao'
    )
  );

create table if not exists public.rag_documentos (
  id uuid primary key default gen_random_uuid(),
  tipo text not null default 'analise_vendas',
  titulo text not null,
  conteudo text not null,
  fonte text,
  tags text[] not null default '{}',
  metadados jsonb not null default '{}'::jsonb,
  status text not null default 'pendente' check (status in ('pendente', 'indexado', 'arquivado')),
  criado_por_usuario_id uuid references public.usuarios(id) on delete set null,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create index if not exists rag_documentos_tipo_status_idx
  on public.rag_documentos (tipo, status, criado_em desc);

create index if not exists rag_documentos_tags_idx
  on public.rag_documentos using gin (tags);

drop trigger if exists rag_documentos_definir_atualizado_em on public.rag_documentos;
create trigger rag_documentos_definir_atualizado_em
before update on public.rag_documentos
for each row execute function public.definir_atualizado_em();

create table if not exists public.rag_trechos (
  id uuid primary key default gen_random_uuid(),
  documento_id uuid not null references public.rag_documentos(id) on delete cascade,
  indice integer not null,
  conteudo text not null,
  tokens_estimados integer,
  metadados jsonb not null default '{}'::jsonb,
  embedding_model text,
  embedding vector(1536),
  criado_em timestamptz not null default now(),
  unique (documento_id, indice)
);

create index if not exists rag_trechos_documento_idx
  on public.rag_trechos (documento_id, indice);
