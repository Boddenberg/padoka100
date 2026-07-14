alter table public.ia_midias_recebidas
  add column if not exists resposta_ia text;

update public.ia_midias_recebidas midia
   set resposta_ia = coalesce(
     nullif(midia.resposta_ia, ''),
     nullif(interacao.dados_confirmacao->>'mensagem_confirmacao', ''),
     nullif(interacao.acao_interpretada->>'mensagem_assistente', '')
   )
  from public.interacoes_ia interacao
 where midia.interacao_ia_id = interacao.id
   and nullif(midia.resposta_ia, '') is null;

comment on column public.ia_midias_recebidas.resposta_ia is
  'Snapshot da mensagem devolvida pela IA ao usuario para a midia recebida.';
