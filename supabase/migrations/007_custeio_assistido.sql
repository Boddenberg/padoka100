create table if not exists public.sessoes_custeio_assistido (
  id uuid primary key default gen_random_uuid(),
  produto_id uuid references public.produtos(id) on delete set null,
  situacao text not null default 'rascunho'
    check (
      situacao in (
        'rascunho',
        'precisa_revisao',
        'pronto_para_confirmar',
        'confirmado',
        'descartado',
        'falhou'
      )
    ),
  rascunho jsonb not null default '{}'::jsonb,
  perguntas jsonb not null default '[]'::jsonb,
  pendencias jsonb not null default '[]'::jsonb,
  avisos jsonb not null default '[]'::jsonb,
  confianca_geral numeric(5, 4) check (confianca_geral is null or confianca_geral between 0 and 1),
  custo_simulado jsonb not null default '{}'::jsonb,
  resultado_confirmacao jsonb,
  mensagem_erro text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  confirmado_em timestamptz,
  descartado_em timestamptz
);

create index if not exists sessoes_custeio_assistido_produto_idx
  on public.sessoes_custeio_assistido (produto_id, criado_em desc);

create index if not exists sessoes_custeio_assistido_situacao_idx
  on public.sessoes_custeio_assistido (situacao);

drop trigger if exists sessoes_custeio_assistido_definir_atualizado_em
  on public.sessoes_custeio_assistido;
create trigger sessoes_custeio_assistido_definir_atualizado_em
before update on public.sessoes_custeio_assistido
for each row execute function public.definir_atualizado_em();

create table if not exists public.entradas_custeio_assistido (
  id uuid primary key default gen_random_uuid(),
  sessao_id uuid not null references public.sessoes_custeio_assistido(id) on delete cascade,
  tipo text not null check (tipo in ('texto', 'audio', 'imagem', 'formulario', 'correcao')),
  texto_original text,
  url_arquivo text,
  nome_arquivo text,
  tipo_conteudo text,
  dados_extraidos jsonb not null default '{}'::jsonb,
  confianca numeric(5, 4) check (confianca is null or confianca between 0 and 1),
  modelo_usado text,
  situacao text not null default 'processada'
    check (situacao in ('recebida', 'processada', 'falhou')),
  mensagem_erro text,
  criado_em timestamptz not null default now()
);

create index if not exists entradas_custeio_assistido_sessao_idx
  on public.entradas_custeio_assistido (sessao_id, criado_em desc);

alter table public.midias
  drop constraint if exists midias_tipo_entidade_check;

alter table public.midias
  add constraint midias_tipo_entidade_check
  check (
    tipo_entidade in (
      'produto',
      'local',
      'dia_de_venda',
      'venda',
      'interacao_ia',
      'usuario',
      'sessao_custeio'
    )
  );
