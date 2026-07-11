-- 014: modelo multiusuario — todo dado de negocio passa a ter dono explicito.
--
-- Estrategia:
--   * usuario_id nas tabelas raiz; tabelas filhas (itens_producao, itens_venda,
--     decisoes_sobra, versoes_preco_produto, insumos_precos, ingredientes_receita,
--     custos_adicionais_produto, entradas_custeio_assistido, correcoes_dia_fechado)
--     herdam o escopo do pai, sempre consultadas a partir de ids ja filtrados.
--   * dados legados (criados antes da autenticacao) pertencem ao primeiro dono
--     real cadastrado; se nao houver dono, ficam sem usuario_id e deixam de
--     aparecer nas consultas (que filtram por usuario_id).
--   * a coluna fica nullable por seguranca com dados de producao; o backend
--     sempre grava usuario_id em registros novos.
--   * sessoes via X-API-Key operam como um usuario de servico com id fixo.

-- 1. Usuario de servico da API key (id fixo conhecido pelo backend).
insert into public.usuarios (id, email, nome, papel, plano, situacao)
values (
  '00000000-0000-0000-0000-000000000001',
  'api-key@padoka.local',
  'API Key',
  'dono',
  'admin',
  'ativo'
)
on conflict (id) do nothing;

-- 2. Coluna de dono nas tabelas raiz.
alter table public.produtos
  add column if not exists usuario_id uuid references public.usuarios(id);
alter table public.locais
  add column if not exists usuario_id uuid references public.usuarios(id);
alter table public.dias_de_venda
  add column if not exists usuario_id uuid references public.usuarios(id);
alter table public.vendas
  add column if not exists usuario_id uuid references public.usuarios(id);
alter table public.interacoes_ia
  add column if not exists usuario_id uuid references public.usuarios(id);
alter table public.insumos
  add column if not exists usuario_id uuid references public.usuarios(id);
alter table public.receitas_produto
  add column if not exists usuario_id uuid references public.usuarios(id);
alter table public.listas_compras
  add column if not exists usuario_id uuid references public.usuarios(id);
alter table public.sessoes_custeio_assistido
  add column if not exists usuario_id uuid references public.usuarios(id);
alter table public.midias
  add column if not exists usuario_id uuid references public.usuarios(id);
alter table public.eventos_linha_do_tempo
  add column if not exists usuario_id uuid references public.usuarios(id);

-- 3. Backfill dos dados legados (idempotente: so linhas sem dono).
do $$
declare
  dono_legado uuid;
begin
  select id
    into dono_legado
    from public.usuarios
   where papel = 'dono'
     and id <> '00000000-0000-0000-0000-000000000001'
   order by criado_em
   limit 1;

  -- Midia de perfil ja indica o proprio dono na entidade.
  update public.midias
     set usuario_id = entidade_id
   where usuario_id is null
     and tipo_entidade = 'usuario'
     and exists (select 1 from public.usuarios u where u.id = midias.entidade_id);

  if dono_legado is null then
    -- Sem dono cadastrado: dados legados ficam sem dono e invisiveis
    -- (consultas filtram por usuario_id). Nada a associar.
    return;
  end if;

  update public.produtos set usuario_id = dono_legado where usuario_id is null;
  update public.locais set usuario_id = dono_legado where usuario_id is null;
  update public.dias_de_venda set usuario_id = dono_legado where usuario_id is null;
  update public.insumos set usuario_id = dono_legado where usuario_id is null;
  update public.listas_compras set usuario_id = dono_legado where usuario_id is null;
  update public.interacoes_ia set usuario_id = dono_legado where usuario_id is null;
  update public.eventos_linha_do_tempo set usuario_id = dono_legado where usuario_id is null;
  update public.midias set usuario_id = dono_legado where usuario_id is null;

  -- Filhas com pai obrigatorio derivam o dono do pai.
  update public.vendas v
     set usuario_id = d.usuario_id
    from public.dias_de_venda d
   where v.usuario_id is null
     and v.dia_de_venda_id = d.id
     and d.usuario_id is not null;

  update public.receitas_produto r
     set usuario_id = p.usuario_id
    from public.produtos p
   where r.usuario_id is null
     and r.produto_id = p.id
     and p.usuario_id is not null;

  update public.sessoes_custeio_assistido s
     set usuario_id = p.usuario_id
    from public.produtos p
   where s.usuario_id is null
     and s.produto_id = p.id
     and p.usuario_id is not null;

  -- Sessoes de custeio sem produto associado tambem eram do dono legado.
  update public.sessoes_custeio_assistido
     set usuario_id = dono_legado
   where usuario_id is null;
end $$;

-- 4. Indices de consulta por dono.
create index if not exists produtos_usuario_idx
  on public.produtos (usuario_id, ordem_exibicao);
create index if not exists locais_usuario_idx
  on public.locais (usuario_id, nome);
create index if not exists dias_de_venda_usuario_data_idx
  on public.dias_de_venda (usuario_id, data_venda desc);
create index if not exists vendas_usuario_idx
  on public.vendas (usuario_id, ocorrido_em desc);
create index if not exists interacoes_ia_usuario_idx
  on public.interacoes_ia (usuario_id, criado_em desc);
create index if not exists insumos_usuario_idx
  on public.insumos (usuario_id, nome);
create index if not exists receitas_produto_usuario_idx
  on public.receitas_produto (usuario_id, criado_em desc);
create index if not exists listas_compras_usuario_idx
  on public.listas_compras (usuario_id, criado_em desc);
create index if not exists sessoes_custeio_usuario_idx
  on public.sessoes_custeio_assistido (usuario_id, criado_em desc);
create index if not exists midias_usuario_idx
  on public.midias (usuario_id, criado_em desc);
create index if not exists eventos_linha_do_tempo_usuario_idx
  on public.eventos_linha_do_tempo (usuario_id, criado_em desc);

-- 5. Slug de produto passa a ser unico por usuario: dois usuarios podem
--    cadastrar produtos com o mesmo nome.
drop index if exists public.produtos_slug_unico_idx;
create unique index if not exists produtos_usuario_slug_unico_idx
  on public.produtos (usuario_id, slug)
  where slug is not null;
