alter table public.midias
  drop constraint if exists midias_tipo_entidade_check;

alter table public.midias
  add constraint midias_tipo_entidade_check
  check (tipo_entidade in ('produto', 'local', 'dia_de_venda', 'venda', 'interacao_ia', 'usuario'));
