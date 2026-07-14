-- Indices dos caminhos usados pelos resumos e pelo Raio-X progressivo.
-- Mantem cada pagina/lote barato mesmo quando o historico cresce.

create index if not exists vendas_usuario_dia_situacao_idx
  on public.vendas (usuario_id, dia_de_venda_id, situacao);

create index if not exists itens_venda_venda_idx
  on public.itens_venda (venda_id);
