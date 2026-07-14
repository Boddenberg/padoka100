-- Relatorios assincronos e imutaveis da area de Analytics.
create table if not exists public.analytics_relatorios (
  id uuid primary key default gen_random_uuid(),
  usuario_id uuid not null references public.usuarios(id) on delete cascade,
  plano_origem text not null
    check (plano_origem in ('analitico', 'ia', 'admin')),
  tipo text not null
    check (tipo in ('analytics', 'ia')),
  data_inicio date not null,
  data_fim date not null,
  status text not null default 'na_fila'
    check (status in ('na_fila', 'processando', 'pronto', 'falhou')),
  progresso smallint not null default 5 check (progresso between 0 and 100),
  etapa text not null default 'Aguardando processamento',
  titulo text,
  conteudo jsonb,
  modelo_ia text,
  erro text,
  export_token uuid not null default gen_random_uuid(),
  solicitado_em timestamptz not null default now(),
  iniciado_em timestamptz,
  concluido_em timestamptz,
  atualizado_em timestamptz not null default now(),
  check (data_fim >= data_inicio),
  check (data_fim - data_inicio <= 365)
);

create index if not exists analytics_relatorios_usuario_historico_idx
  on public.analytics_relatorios (usuario_id, solicitado_em desc);

create index if not exists analytics_relatorios_fila_idx
  on public.analytics_relatorios (status, solicitado_em)
  where status in ('na_fila', 'processando');

create unique index if not exists analytics_relatorios_usuario_ativo_idx
  on public.analytics_relatorios (usuario_id)
  where status in ('na_fila', 'processando');

drop trigger if exists analytics_relatorios_definir_atualizado_em
  on public.analytics_relatorios;
create trigger analytics_relatorios_definir_atualizado_em
before update on public.analytics_relatorios
for each row execute function public.definir_atualizado_em();
