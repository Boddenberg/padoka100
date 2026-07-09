alter table public.versoes_preco_produto
  add column if not exists origem text not null default 'manual',
  add column if not exists gerado_por_ia boolean not null default false;

update public.versoes_preco_produto
set origem = 'ia',
    gerado_por_ia = true
where lower(coalesce(motivo, '')) like '%assistente%';

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'versoes_preco_produto_origem_check'
      and conrelid = 'public.versoes_preco_produto'::regclass
  ) then
    alter table public.versoes_preco_produto
      add constraint versoes_preco_produto_origem_check
      check (origem in ('manual', 'ia'));
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'versoes_preco_produto_origem_ia_consistente_check'
      and conrelid = 'public.versoes_preco_produto'::regclass
  ) then
    alter table public.versoes_preco_produto
      add constraint versoes_preco_produto_origem_ia_consistente_check
      check (gerado_por_ia = (origem = 'ia'));
  end if;
end $$;
