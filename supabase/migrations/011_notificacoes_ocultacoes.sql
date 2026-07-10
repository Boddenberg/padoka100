create table if not exists public.notificacao_ocultacoes (
  id uuid primary key default gen_random_uuid(),
  notificacao_id uuid not null references public.notificacoes(id) on delete cascade,
  usuario_id uuid not null references public.usuarios(id) on delete cascade,
  ocultado_em timestamptz not null default now(),
  unique (notificacao_id, usuario_id)
);

create index if not exists notificacao_ocultacoes_notificacao_idx
  on public.notificacao_ocultacoes (notificacao_id, ocultado_em desc);

create index if not exists notificacao_ocultacoes_usuario_idx
  on public.notificacao_ocultacoes (usuario_id, ocultado_em desc);

create index if not exists notificacao_visualizacoes_usuario_idx
  on public.notificacao_visualizacoes (usuario_id, visualizado_em desc);
