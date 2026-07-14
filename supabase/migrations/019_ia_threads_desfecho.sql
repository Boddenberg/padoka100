alter table public.interacoes_ia
  add column if not exists thread_id uuid;

update public.interacoes_ia
   set thread_id = gen_random_uuid()
 where thread_id is null;

alter table public.interacoes_ia
  alter column thread_id set default gen_random_uuid();

alter table public.interacoes_ia
  add column if not exists resolvido_em timestamptz,
  add column if not exists motivo_rejeicao text;

update public.interacoes_ia
   set resolvido_em = criado_em
 where resolvido_em is null
   and situacao in ('confirmada', 'rejeitada', 'falhou');

create index if not exists interacoes_ia_thread_data_idx
  on public.interacoes_ia (thread_id, criado_em asc);

alter table public.ia_midias_recebidas
  add column if not exists thread_id uuid;

update public.ia_midias_recebidas midia
   set thread_id = interacao.thread_id
  from public.interacoes_ia interacao
 where midia.interacao_ia_id = interacao.id
   and midia.thread_id is null;

update public.ia_midias_recebidas
   set thread_id = gen_random_uuid()
 where thread_id is null;

alter table public.ia_midias_recebidas
  alter column thread_id set default gen_random_uuid();

create index if not exists ia_midias_recebidas_thread_data_idx
  on public.ia_midias_recebidas (thread_id, criado_em asc);

comment on column public.interacoes_ia.thread_id is
  'Agrupa tentativas e respostas de IA que pertencem a uma mesma conversa do usuario.';

comment on column public.interacoes_ia.resolvido_em is
  'Quando a interacao saiu do estado pendente: confirmada, rejeitada ou falhou.';

comment on column public.interacoes_ia.motivo_rejeicao is
  'Motivo informado quando o usuario descartou uma interpretacao da IA.';
