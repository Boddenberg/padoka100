-- Canal de reports do usuario: erro, dificuldade de uso, sugestao ou recado.
-- O texto e os metadados moram aqui; anexos (print, foto, audio) reaproveitam a
-- tabela `midias` com tipo_entidade = 'report'.

create table if not exists public.reports (
  id uuid primary key default gen_random_uuid(),
  usuario_id uuid references public.usuarios(id) on delete set null,
  tipo text not null default 'recado'
    check (tipo in ('erro', 'dificuldade', 'sugestao', 'recado')),
  mensagem text,
  contexto text,
  plataforma text,
  app_versao text,
  status text not null default 'novo'
    check (status in ('novo', 'lido', 'resolvido')),
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create index if not exists reports_criado_em_idx
  on public.reports (criado_em desc);

create index if not exists reports_status_idx
  on public.reports (status, criado_em desc);

create index if not exists reports_usuario_idx
  on public.reports (usuario_id);

-- Libera anexos de report na tabela de midias (mesmo padrao dos demais tipos).
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
      'notificacao',
      'report'
    )
  );
