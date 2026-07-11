# Notificacoes: guia para o front

Todas as rotas abaixo ficam em `/api/v1`. No front, envie sempre:

```http
Authorization: Bearer <access_token>
```

## Fluxo recomendado

O front deve usar **uma chamada principal** para montar o sino/lista de
notificacoes:

```http
GET /notificacoes/feed?limite=20&incluir_lidas=true
```

Nao envie `usuario_id` no request. O backend pega o usuario pelo Bearer token e
ja mistura, na ordem certa:

- notificacoes globais (`todos`);
- notificacoes do plano do usuario (`plano`);
- notificacoes individuais (`usuario_alvo_id`);
- estado de leitura/ocultacao daquele usuario.

Resposta enxuta para a UI:

```json
{
  "itens": [
    {
      "id": "NOTIFICACAO_ID",
      "titulo": "Aviso",
      "corpo": "Texto da notificacao",
      "prioridade": "normal",
      "publicado_em": "2026-07-11T12:00:00Z",
      "expira_em": "2026-07-18T12:00:00Z",
      "criado_em": "2026-07-11T11:50:00Z",
      "lida": false,
      "lida_em": null,
      "nova": true,
      "midias": [
        {
          "url": "https://...",
          "descricao": "Imagem do aviso"
        }
      ]
    }
  ],
  "resumo": {
    "total": 12,
    "nao_lidas": 4,
    "lidas": 8,
    "novas": 4,
    "retornadas": 10
  },
  "limite": 10,
  "tem_mais": true,
  "persistida": true
}
```

Ordem do feed:

- itens ocultos pelo usuario nao entram;
- expiradas nao entram;
- nao lidas entram antes das lidas;
- dentro de cada grupo, `prioridade: "alta"` vem antes de `normal`, depois
  `baixa`;
- dentro da mesma prioridade, as mais recentes vem primeiro;
- se houver nao lidas suficientes para preencher `limite`, o feed volta so nao
  lidas;
- lidas so ocupam o restante quando sobrar espaco no `limite`.

Campos que o front deve usar:

- `itens`: lista renderizavel.
- `resumo.nao_lidas`: badge do sino.
- `item.nova`: destaque visual para item ainda nao lido.
- `item.prioridade`: cor/icone de urgencia, se quiser.
- `tem_mais`: mostrar "ver mais" ou aumentar `limite`.

Campos internos que o backend **nao** manda no feed: `publico`, `planos_alvo`,
`usuario_alvo_id`, `status`, `metadados`, `criado_por_usuario_id`.

## Acoes do usuario

As acoes continuam separadas porque acontecem por clique:

```http
POST /notificacoes/{id}/lida
POST /notificacoes/{id}/ler
POST /notificacoes/{id}/nao-lida
POST /notificacoes/{id}/ocultar
```

Resposta:

```json
{
  "notificacao_id": "NOTIFICACAO_ID",
  "lida": true,
  "lida_em": "2026-07-11T12:10:00Z",
  "oculta": false,
  "oculta_em": null,
  "persistida": true
}
```

Depois de qualquer acao, chame novamente:

```http
GET /notificacoes/feed?limite=20
```

`ocultar` deve remover o item da tela no proximo feed.

## Rotas antigas/compatibilidade

Estas rotas continuam existindo, mas o front novo deve preferir
`/notificacoes/feed`:

```http
GET /notificacoes?limite=50&incluir_lidas=true&incluir_ocultas=false
GET /notificacoes/nao-lidas/contagem
GET /notificacoes/{id}
```

Resposta de `GET /notificacoes`:

```json
[
  {
    "id": "NOTIFICACAO_ID",
    "titulo": "Aviso",
    "corpo": "Texto da notificacao",
    "prioridade": "normal",
    "publicado_em": "2026-07-11T12:00:00Z",
    "expira_em": "2026-07-18T12:00:00Z",
    "criado_em": "2026-07-11T11:50:00Z",
    "lida": false,
    "lida_em": null,
    "nova": true,
    "midias": [
      {
        "url": "https://...",
        "descricao": "Imagem do aviso"
      }
    ]
  }
]
```

## Regras de visibilidade

- `publico: "todos"` aparece para qualquer usuario autenticado.
- `publico: "plano"` aparece quando o plano do usuario esta em `planos_alvo`.
- `publico: "usuario"` aparece apenas para `usuario_alvo_id`.
- notificacao expirada (`expira_em` menor que agora) nao aparece.
- notificacao oculta pelo usuario nao aparece no feed.

## Criacao admin

Criar para todos, sem expiracao:

```http
POST /admin/notificacoes
Content-Type: application/json
```

```json
{
  "titulo": "Atualizacao no sistema",
  "corpo": "Texto da mensagem.",
  "publico": "todos",
  "publicar_agora": true
}
```

Criar para um plano, expirando em 7 dias:

```json
{
  "titulo": "Recurso novo do plano IA",
  "corpo": "Mensagem para clientes do plano IA.",
  "publico": "plano",
  "planos_alvo": ["ia"],
  "publicar_agora": true,
  "expira_em_dias": 7
}
```

Criar para uma pessoa especifica:

```json
{
  "titulo": "Aviso individual",
  "corpo": "Mensagem exclusiva para esta conta.",
  "publico": "usuario",
  "usuario_alvo_id": "UUID_DO_USUARIO",
  "publicar_agora": true
}
```

Tambem continua valido usar uma data absoluta:

```json
{
  "titulo": "Campanha",
  "corpo": "Mensagem com data fixa.",
  "publico": "todos",
  "publicar_agora": true,
  "expira_em": "2026-07-31T23:59:59Z"
}
```

Use `expira_em` ou `expira_em_dias`, nunca os dois. Se nenhum for enviado, a
notificacao nao expira.

Planos aceitos em `planos_alvo`:

```json
["basico", "analitico", "ia", "admin"]
```

## Gestao admin

Listar admin:

```http
GET /admin/notificacoes?status=publicada&limite=100
```

Editar:

```http
PATCH /admin/notificacoes/{id}
```

Publicar rascunho:

```http
POST /admin/notificacoes/{id}/publicar
```

Arquivar:

```http
POST /admin/notificacoes/{id}/arquivar
```

Excluir definitivamente:

```http
DELETE /admin/notificacoes/{id}
```

Resposta esperada: `204 No Content`.

Limpar expiradas do banco:

```http
DELETE /admin/notificacoes/expiradas
```

Resposta:

```json
{
  "removidas": 12
}
```
