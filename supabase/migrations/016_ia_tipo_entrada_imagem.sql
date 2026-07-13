-- interacoes_ia.tipo_entrada passa a aceitar 'imagem'.
-- As rotas de foto (cardapio e producao por imagem) gravam tipo_entrada
-- = 'imagem', mas a constraint original so permitia ('texto', 'audio'),
-- o que causava violacao de check (23514) e 500 no importar-cardapio.
-- Recria a constraint de forma idempotente com o valor novo.
alter table public.interacoes_ia
  drop constraint if exists interacoes_ia_tipo_entrada_check;

alter table public.interacoes_ia
  add constraint interacoes_ia_tipo_entrada_check
  check (tipo_entrada in ('texto', 'audio', 'imagem'));
