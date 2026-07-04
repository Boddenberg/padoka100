# Plano de implementacao da Padoka 100 API

## Objetivo

Criar uma API backend pronta para o futuro app web/mobile da Padoka 100, com foco em uso visual, simples e historico confiavel.

A API deve permitir que uma pessoa com pouca intimidade com tecnologia consiga operar a rotina por telas muito diretas:

1. Cadastrar produtos com nome, descricao, foto e preco.
2. Abrir o dia de venda.
3. Informar a producao do dia.
4. Registrar vendas por botoes grandes ou por audio.
5. Fechar o dia.
6. Consultar historico por dia, produto e local.

## Decisoes de stack

- **FastAPI** para API HTTP, documentacao automatica em `/docs` e boa ergonomia com apps mobile/web.
- **Supabase Postgres** como banco principal.
- **Supabase Storage** para imagens de produtos, locais, comprovantes, fotos do dia e audios.
- **OpenAI API** como camada de interpretacao de comandos. A IA nao grava venda sozinha: ela traduz texto/audio para uma intencao estruturada, e a API retorna uma confirmacao para o front.

## Principios de produto

- Visual primeiro: produtos precisam ter foto, descricao curta, descricao visual e cor/ordem para facilitar botoes grandes no front.
- Historico imutavel: venda antiga nunca muda quando nome, foto, custo ou preco do produto mudam.
- Confirmacao antes de acao sensivel: comandos interpretados por IA retornam payload de confirmacao antes de salvar.
- Desfazer sem apagar: venda errada deve ser marcada como cancelada, nao deletada.
- Dia de venda como centro do sistema: relatatorios e consultas partem de `sales_days`.

## Modelo de historico de preco

Produtos ficam em `products`.

Precos ficam em `product_price_versions`, com:

- `effective_from`
- `effective_to`
- `sale_price`
- `cost_price`
- `reason`

Quando um preco novo entra, a versao anterior e encerrada no dia anterior. As vendas salvas guardam snapshots:

- nome do produto no momento
- imagem principal no momento
- preco de venda no momento
- custo no momento
- id da versao de preco usada

Isso garante que relatorios antigos continuem corretos.

## Modulos da API

### Produtos

- Cadastrar produto.
- Listar produtos ativos.
- Atualizar dados visuais/descritivos.
- Adicionar nova versao de preco.
- Listar historico de precos.
- Enviar fotos do produto.

### Locais

- Cadastrar condominios/locais.
- Associar local a um dia de venda.
- Guardar snapshot do nome do local no dia.

### Dias de venda

- Abrir dia.
- Adicionar/editar producao.
- Registrar observacoes.
- Fechar dia.
- Consultar dia aberto.

### Vendas

- Registrar venda manual.
- Registrar venda derivada de IA.
- Cancelar venda sem apagar historico.
- Listar vendas de um dia.

### Relatorios

- Resumo do dia.
- Resumo semanal.
- Produtos mais vendidos.
- Sobras por produto.
- Receita, custo estimado e lucro estimado.

### IA/audio

- Interpretar comando textual.
- Transcrever audio.
- Transcrever audio e interpretar venda.
- Salvar interacoes em `ai_interactions`.

## Ordem de construcao

1. Scaffold do projeto Python/FastAPI.
2. Configuracao, clientes Supabase/OpenAI e tratamento de erros.
3. Schema SQL do Supabase.
4. Modulo de produtos e historico de preco.
5. Modulo de dias de venda/producao.
6. Modulo de vendas e cancelamento.
7. Relatorios calculados.
8. Upload de midia.
9. IA para interpretar comandos.
10. Documentacao de uso e variaveis de ambiente.

