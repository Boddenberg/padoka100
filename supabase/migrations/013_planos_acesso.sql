alter table public.usuarios
  add column if not exists plano text not null default 'basico';

alter table public.usuarios
  drop constraint if exists usuarios_plano_check;

alter table public.usuarios
  add constraint usuarios_plano_check
  check (plano in ('basico', 'analitico', 'ia', 'admin'));

create index if not exists usuarios_plano_idx
  on public.usuarios (plano);
