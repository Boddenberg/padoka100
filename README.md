# Padoka 100

Backend em Python/FastAPI para apoiar a rotina de uma pequena padaria familiar.

O sistema deve ser simples para quem vende no dia a dia e bem estruturado por
dentro para evoluir com seguranca. A API guarda catalogo, venda do dia,
historico, relatorios, midia, comandos por IA e bases futuras para perfil,
permissoes, analises e custos reais de produtos.

Este README e a referencia atual do produto e da arquitetura. Antes de criar
novas funcionalidades grandes, alinhe aqui o plano geral, as regras de negocio e
os contratos esperados.

## Tecnologias reais do projeto

- Linguagem: Python 3.12+
- Framework: FastAPI
- Banco de dados: Supabase Postgres
- Storage: Supabase Storage, bucket `padoka-midia`
- ORM/ODM: nenhum no momento; acesso via cliente oficial `supabase-py`
- Validacao/DTOs: Pydantic
- Autenticacao atual: API key opcional via header `X-API-Key`
- Autenticacao planejada: usuario/e-mail e senha, sessao ou token, troca de senha e permissoes
- IA: OpenAI API para interpretar comandos de texto/audio e, futuramente, analises
- Testes: ainda sem suite automatizada; `ruff` configurado para lint
- Gerenciador/empacotamento: `pip`, `pyproject.toml`, Hatchling
- Ambiente: variaveis em `.env` via `pydantic-settings`
- Deploy: configuracoes para Render (`render.yaml`) e Railway (`railway.json`)

## Rodando localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
uvicorn app.main:app --reload
```

Depois de configurar as chaves no `.env`, aplique os SQLs de
`supabase/migrations` em ordem no projeto Supabase.

A documentacao interativa fica em:

- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

## Endpoints principais

- `GET /health`
- `GET /api/v1/produtos`
- `POST /api/v1/produtos`
- `GET /api/v1/produtos/{produto_id}`
- `PATCH /api/v1/produtos/{produto_id}`
- `GET /api/v1/produtos/{produto_id}/precos`
- `POST /api/v1/produtos/{produto_id}/precos`
- `POST /api/v1/produtos/{produto_id}/midia`
- `GET /api/v1/locais`
- `POST /api/v1/locais`
- `GET /api/v1/locais/{local_id}`
- `PATCH /api/v1/locais/{local_id}`
- `GET /api/v1/dias-de-venda`
- `POST /api/v1/dias-de-venda`
- `GET /api/v1/dias-de-venda/atual`
- `POST /api/v1/dias-de-venda/iniciar-hoje`
- `GET /api/v1/dias-de-venda/{dia_de_venda_id}`
- `PATCH /api/v1/dias-de-venda/{dia_de_venda_id}`
- `POST /api/v1/dias-de-venda/{dia_de_venda_id}/itens-producao`
- `POST /api/v1/dias-de-venda/{dia_de_venda_id}/fechar`
- `POST /api/v1/dias-de-venda/{dia_de_venda_id}/correcoes`
- `POST /api/v1/vendas`
- `GET /api/v1/vendas/por-dia/{dia_de_venda_id}`
- `GET /api/v1/vendas/{venda_id}`
- `POST /api/v1/vendas/{venda_id}/cancelar`
- `GET /api/v1/relatorios/dias/{dia_de_venda_id}/resumo`
- `GET /api/v1/relatorios/dias/por-data/{data_venda}/resumo`
- `GET /api/v1/relatorios/dias/{dia_de_venda_id}/produtos-venda`
- `GET /api/v1/relatorios/periodo`
- `GET /api/v1/historico/linha-do-tempo`
- `POST /api/v1/midia/{tipo_entidade}/{entidade_id}`
- `POST /api/v1/ia/interpretar-comando`
- `POST /api/v1/ia/transcrever-audio`
- `POST /api/v1/ia/interacoes/{interacao_ia_id}/confirmar`
- `POST /api/v1/ia/interpretar-comando-de-venda`
- `POST /api/v1/ia/transcrever-audio-de-venda`
- `POST /api/v1/ia/interacoes/{interacao_ia_id}/confirmar-venda`
- `GET /api/v1/ia/dados-estruturados/periodo`
- `POST /api/v1/ia/analises/padrao`
- `POST /api/v1/ia/analises/especifica`
- `POST /api/v1/auth/registrar`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/trocar-senha`
- `GET /api/v1/auth/usuarios`
- `PATCH /api/v1/auth/usuarios/{usuario_id}/papel`
- `GET /api/v1/perfil/me`
- `PATCH /api/v1/perfil/me`
- `POST /api/v1/perfil/me/foto`
- `GET /api/v1/custos/insumos`
- `POST /api/v1/custos/insumos`
- `PATCH /api/v1/custos/insumos/{insumo_id}`
- `GET /api/v1/custos/produtos/{produto_id}/receitas`
- `POST /api/v1/custos/produtos/{produto_id}/receitas`
- `POST /api/v1/custos/produtos/{produto_id}/custos-adicionais`
- `GET /api/v1/custos/produtos/{produto_id}/calculo`

Exemplos de uso ficam em `docs/API_USAGE.md`.

Compatibilidade de autenticacao: endpoints antigos de produtos, midia,
dias de venda, vendas, relatorios, historico, correcoes e IA operacional nao
exigem Bearer token. As rotas novas de perfil/seguranca, gestao de usuarios,
analises/dados estruturados de IA e custos exigem Bearer token conforme o papel.

## Regras de negocio centrais

### Catalogo e venda do dia

O catalogo contem todos os produtos cadastrados.

A venda do dia deve mostrar somente produtos que participaram daquele dia:

- entrou na venda do dia: aparece;
- entrou e esgotou: continua aparecendo como esgotado;
- nunca entrou no dia: nao aparece na aba de venda.

### Historico e snapshots

Preco e historico nao devem ser reescritos sem rastro.

Quando o preco de um produto muda, o backend cria uma nova versao de preco.
Vendas e producoes salvam snapshots do nome, imagem e preco daquele dia. Assim,
se o pao de calabresa custava R$ 8,00 na segunda e mudou para R$ 10,00 na
quinta, a segunda continua mostrando R$ 8,00 para sempre.

### Dia fechado e correcao retroativa

Dia fechado pode ser corrigido, mas nao deve ser simplesmente reaberto sem
controle. Correcoes de dias fechados precisam preservar:

- dado original;
- dado corrigido;
- usuario que corrigiu, quando existir autenticacao;
- data da correcao;
- motivo opcional;
- alteracoes em formato estruturado.

### Datas futuras

Consultas, resumos e analises nao devem aceitar periodo futuro. Mesmo que o
front bloqueie visualmente, a API deve validar a data final no backend.

## Estado atual

Ja existe:

- estrutura FastAPI com `app.main:app`, CORS, healthcheck e configuracao por `.env`;
- modulos em portugues dentro de `app/modules`;
- integracao com Supabase e OpenAI;
- migrations SQL para schema inicial, sobras, correcoes, auth/perfil, custos e midia de usuario;
- cadastro, listagem, atualizacao e consulta de produtos;
- historico de precos por versao;
- cadastro e atualizacao de locais;
- abertura, edicao, consulta e fechamento de dias de venda;
- virada de dia com decisao explicita sobre sobras;
- registro de producao com snapshot de produto, imagem e preco;
- registro de vendas manuais com snapshots de nome, imagem, preco e custo;
- cancelamento de venda sem apagar historico;
- correcao retroativa de dias fechados;
- relatorios por dia, data e periodo;
- consulta de produtos que participaram da venda do dia;
- bloqueio de datas futuras em consultas sensiveis;
- historico estruturado para o front;
- upload de midia;
- interpretacao de comandos por texto/audio com confirmacao antes de salvar;
- autenticacao real com senha hash PBKDF2, bearer token e logout;
- perfil do usuario com foto, upload de foto, nome, nascimento, telefone e e-mail;
- papeis `usuario`, `administrador` e `dono` em rotas novas sensiveis;
- dados estruturados para IA por periodo;
- analise padrao e especifica com secoes estruturadas e resumo local quando OpenAI nao estiver configurada;
- modulo inicial de custos com insumos, receitas, custos adicionais e calculo por produto.

Ainda nao existe como funcionalidade completa:

- extracao de nota fiscal por foto;
- testes automatizados de integracao.

## Autenticacao e perfil planejados

A autenticacao precisa entrar como funcionalidade real antes de expor o sistema a
usuarios finais. O backend deve suportar:

- criacao de usuario;
- login com usuario/e-mail e senha;
- armazenamento seguro de senha;
- autenticacao por token ou sessao;
- protecao de rotas;
- identificacao do usuario autenticado;
- logout, se aplicavel;
- troca de senha;
- alteracao de e-mail ou usuario;
- sessao expirada;
- validacao de permissoes.

O perfil do usuario deve armazenar:

- foto;
- nome;
- data de nascimento;
- telefone;
- e-mail.

Esses dados podem ajudar a IA futuramente a personalizar respostas e entender o
contexto da conta, mas a IA nao deve depender deles para inventar informacoes.

## Permissoes futuras

A arquitetura deve permitir papeis diferentes no futuro:

- Usuario comum: pode vender e consultar dados basicos.
- Administrador: pode corrigir dias fechados e alterar cadastro de produtos.
- Dono: pode consultar relatorios, IA e dados financeiros.

Nao e necessario implementar todos os papeis imediatamente, mas os proximos
modulos devem ser desenhados para receber verificacao de permissao sem reescrita
grande.

## Dados estruturados para IA

A IA nao deve receber dados crus e baguncados do banco. O backend deve montar
estruturas por:

- dia;
- semana;
- mes;
- periodo personalizado;
- produto;
- categoria, se existir futuramente.

Resumo diario conceitual:

```json
{
  "data": "2026-07-08",
  "faturamentoTotal": 650,
  "quantidadeTotalProduzida": 46,
  "quantidadeTotalVendida": 25,
  "quantidadeTotalSobrando": 21,
  "produtos": [
    {
      "produto": "Pao de Queijo",
      "quantidadeProduzida": 20,
      "quantidadeVendida": 20,
      "quantidadeSobrando": 0,
      "faturamento": 300
    }
  ]
}
```

Resumo por periodo conceitual:

```json
{
  "periodo": {
    "inicio": "2026-07-01",
    "fim": "2026-07-08"
  },
  "faturamentoTotal": 3200,
  "quantidadeTotalVendida": 140,
  "produtos": [
    {
      "produto": "Pao de Queijo",
      "totalProduzido": 100,
      "totalVendido": 90,
      "totalSobrando": 10,
      "faturamento": 1350
    }
  ]
}
```

Essas estruturas devem indicar se houve correcoes retroativas, produtos
esgotados, sobras altas, dias sem venda e dados incompletos.

## Analises com IA

### Analise padrao

O front seleciona um periodo, como julho, e pede uma analise geral. O backend
deve montar os dados estruturados do periodo e enviar para a IA responder com
base nos fatos salvos.

A analise padrao deve considerar:

- faturamento;
- produtos vendidos;
- produtos produzidos;
- sobras;
- produtos esgotados;
- comparacao entre dias;
- historico de vendas;
- correcoes retroativas relevantes.

### Analise especifica

Alem da analise padrao, o backend deve aceitar pedidos especificos do usuario,
como:

- analise somente abril;
- ignore os pudins;
- veja so o pao de calabresa;
- compare pao de queijo com pao sovado;
- diga o que mais sobrou;
- diga o que deveria ser produzido menos.

O backend deve receber periodo, contexto opcional, dados estruturados e filtros
solicitados. A IA deve responder somente com base nesses dados e deixar claro
quando algo nao estiver disponivel.

## Custos reais dos produtos

O calculo de custo dos produtos sera uma das partes mais complexas do projeto.
O sistema precisa permitir que o dono informe dados aos poucos, com status de
confianca.

Informacoes que o backend deve conseguir guardar:

- insumos comprados;
- preco dos insumos;
- quantidade comprada;
- unidade de medida;
- receita do produto;
- quantidade usada na receita;
- rendimento da receita;
- custos indiretos;
- embalagem;
- transporte;
- status de confirmacao das informacoes.

Exemplo de insumo:

```json
{
  "nome": "Farinha de trigo",
  "quantidadeComprada": 1,
  "unidadeCompra": "kg",
  "precoTotal": 5.0,
  "custoPorUnidade": 5.0
}
```

Exemplo de receita:

```json
{
  "produto": "Pao Sovado",
  "rendimento": 10,
  "ingredientes": [
    {
      "nome": "Farinha de trigo",
      "quantidadeUsada": 800,
      "unidade": "g"
    },
    {
      "nome": "Leite",
      "quantidadeUsada": 300,
      "unidade": "ml"
    }
  ]
}
```

Exemplo de custo calculado:

```json
{
  "produto": "Pao Sovado",
  "custoTotalReceita": 28.5,
  "rendimento": 10,
  "custoPorUnidade": 2.85,
  "custosIncluidos": {
    "ingredientes": true,
    "embalagem": true,
    "gas": true,
    "energia": false,
    "transporte": false
  },
  "status": "CONFIRMADO"
}
```

Status possiveis para dados de custo:

- `CONFIRMADO`
- `ESTIMADO`
- `PENDENTE`
- `PRECISA_REVISAR`

Custos que devem poder entrar no calculo:

- ingredientes principais: farinha, leite, ovos, queijo, calabresa, presunto,
  frango, acucar, manteiga, oleo e fermento;
- ingredientes pequenos: sal, temperos, oregano, alho, cebola e essencia;
- custos indiretos: gas, energia eletrica, agua, tempo de forno,
  geladeira/freezer e desgaste de equipamento futuramente;
- embalagem: saquinho, bandeja, etiqueta, caixa, papel e plastico filme;
- transporte: gasolina, estacionamento, frete e taxa de entrega.

A IA pode ajudar a montar custos, mas nao pode inventar dados:

- se nao souber, pergunta;
- se for estimativa, marca como estimativa;
- se for confirmado pelo usuario, marca como confirmado;
- antes de salvar, sempre pede confirmacao.

Entradas futuras podem vir por texto, audio, foto de nota fiscal, formulario ou
correcao posterior. Foto ruim ou leitura insegura deve gerar pedido de
confirmacao manual.

## Arquitetura atual

Estrutura real do projeto hoje:

```txt
app/
  api/
    router.py
  core/
    config.py
    errors.py
  db/
    openai.py
    supabase.py
  modules/
    dias_de_venda/
    historico/
    ia/
    locais/
    midia/
    produtos/
    relatorios/
    vendas/
  shared/
    datas.py
    db.py
    esquemas.py
    linha_do_tempo.py
    slugs.py
supabase/
  migrations/
docs/
```

Padrao atual:

- rotas FastAPI em `router.py`;
- regras de negocio em `servico.py`;
- DTOs/response models em `esquemas.py`;
- acesso ao Supabase dentro dos servicos;
- helpers compartilhados em `app/shared`;
- tratamento de erro padronizado em `app/core/errors.py`.

## Arquitetura desejada

Nao e necessario mudar tudo de uma vez. A direcao desejada e separar melhor:

- entrada HTTP;
- regra de negocio;
- acesso a dados;
- validacao;
- autenticacao;
- autorizacao;
- resposta para o front-end.

Adaptacao sugerida para o projeto atual:

```txt
app/
  api/
  auth/
  core/
  db/
  modules/
    produtos/
      router.py
      servico.py
      repositorio.py
      esquemas.py
    vendas/
    catalogo/
    resumo/
    historico/
    perfil/
    ia/
    custos/
  shared/
  tests/
```

Ao criar novos modulos, preferir:

- manter rotas finas;
- deixar regra de negocio nos servicos;
- criar repositorios quando o acesso ao banco ficar repetido ou complexo;
- manter schemas de entrada e saida explicitos;
- validar regra sensivel no backend, nao so no front;
- registrar historico de alteracoes relevantes;
- documentar endpoints novos em `docs/API_USAGE.md`.

## Panorama futuro

O backend deve evoluir para uma base simples de apoio a decisao. No futuro, o
sistema deve ajudar a responder:

- quanto vendemos hoje?
- quanto vendemos no mes?
- o que mais vende?
- o que mais sobra?
- o que devemos produzir menos?
- o que devemos produzir mais?
- qual produto da mais lucro?
- qual produto custa mais caro para produzir?
- existe padrao por dia da semana?
- a producao esta acima ou abaixo do ideal?

## Proximos passos recomendados

1. Revisar e confirmar este README como referencia de produto.
2. Definir o modelo de autenticacao e perfil antes de implementar rotas novas.
3. Definir papeis e permissoes minimos para a primeira versao.
4. Especificar contratos de dados estruturados para IA.
5. Especificar o modelo de custos, insumos e receitas antes da migration.
6. Criar testes para fluxos centrais antes de ampliar o modulo financeiro.
7. Aplicar as migrations no Supabase real e testar ponta a ponta.
