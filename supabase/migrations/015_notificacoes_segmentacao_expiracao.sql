alter table public.notificacoes
  add column if not exists planos_alvo text[] not null default '{}',
  add column if not exists usuario_alvo_id uuid references public.usuarios(id) on delete set null,
  add column if not exists expira_em_dias integer;

update public.notificacoes
   set planos_alvo = '{}'
 where planos_alvo is null;

alter table public.notificacoes
  alter column planos_alvo set default '{}',
  alter column planos_alvo set not null;

alter table public.notificacoes
  drop constraint if exists notificacoes_publico_check;

alter table public.notificacoes
  add constraint notificacoes_publico_check
  check (publico in ('todos', 'admins', 'plano', 'usuario'));

alter table public.notificacoes
  drop constraint if exists notificacoes_planos_alvo_check;

alter table public.notificacoes
  add constraint notificacoes_planos_alvo_check
  check (planos_alvo <@ array['basico', 'analitico', 'ia', 'admin']::text[]);

alter table public.notificacoes
  drop constraint if exists notificacoes_expira_em_dias_check;

alter table public.notificacoes
  add constraint notificacoes_expira_em_dias_check
  check (expira_em_dias is null or expira_em_dias > 0);

alter table public.notificacoes
  drop constraint if exists notificacoes_alvo_check;

alter table public.notificacoes
  add constraint notificacoes_alvo_check
  check (
    (
      publico in ('todos', 'admins')
      and cardinality(planos_alvo) = 0
      and usuario_alvo_id is null
    )
    or (
      publico = 'plano'
      and cardinality(planos_alvo) > 0
      and usuario_alvo_id is null
    )
    or (
      publico = 'usuario'
      and cardinality(planos_alvo) = 0
      and usuario_alvo_id is not null
    )
  );

create index if not exists notificacoes_usuario_alvo_idx
  on public.notificacoes (usuario_alvo_id, publicado_em desc)
  where publico = 'usuario';

create index if not exists notificacoes_planos_alvo_idx
  on public.notificacoes using gin (planos_alvo);

create index if not exists notificacoes_expira_em_idx
  on public.notificacoes (expira_em)
  where expira_em is not null;

create index if not exists notificacoes_feed_idx
  on public.notificacoes (status, publicado_em desc, criado_em desc);
