create table if not exists public.ia_midias_recebidas (
  id uuid primary key default gen_random_uuid(),
  usuario_id uuid references public.usuarios(id) on delete set null,
  usuario_nome_cadastrado text,
  item text not null check (item in ('audio', 'foto')),
  interacao_ia_id uuid references public.interacoes_ia(id) on delete set null,
  midia_id uuid references public.midias(id) on delete set null,
  nome_arquivo text,
  url_publica text,
  tipo_conteudo text,
  criado_em timestamptz not null default now()
);

create index if not exists ia_midias_recebidas_usuario_data_idx
  on public.ia_midias_recebidas (usuario_id, criado_em desc);

create index if not exists ia_midias_recebidas_item_data_idx
  on public.ia_midias_recebidas (item, criado_em desc);

create index if not exists ia_midias_recebidas_interacao_idx
  on public.ia_midias_recebidas (interacao_ia_id)
  where interacao_ia_id is not null;
