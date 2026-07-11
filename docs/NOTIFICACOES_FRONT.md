# Notificacoes: guia para o front

Todas as rotas abaixo ficam em `/api/v1`. No front, envie sempre:

```http
Authorization: Bearer <access_token>
```

## Feed do usuario

Listar notificacoes visiveis para o usuario logado:

```http
GET /notificacoes?limite=50&incluir_lidas=true&incluir_ocultas=false
```

Resposta:

```json
[
  {
    "id": "NOTIFICACAO_ID",
    "titulo": "Aviso",
    "corpo": "Texto da notificacao",
    "publicado_em": "2026-07-11T12:00:00Z",
    "expira_em": "2026-07-18T12:00:00Z",
    "criado_em": "2026-07-11T11:50:00Z",
    "lida": false,
    "lida_em": null,
    "midias": [
      {
        "url": "https://...",
        "descricao": "Imagem do aviso"
      }
    ]
  }
]
```

Regras do feed:

- `publico: "todos"` aparece para qualquer usuario autenticado.
- `publico: "plano"` aparece quando o plano do usuario esta em `planos_alvo`.
- `publico: "usuario"` aparece apenas para `usuario_alvo_id`.
- notificacao expirada (`expira_em` menor que agora) nao aparece.
- notificacao oculta pelo usuario nao aparece quando `incluir_ocultas=false`.

Contar nao lidas:

```http
GET /notificacoes/nao-lidas/contagem
```

Marcar/desmarcar/ocultar:

```http
POST /notificacoes/{id}/lida
POST /notificacoes/{id}/ler
POST /notificacoes/{id}/nao-lida
POST /notificacoes/{id}/ocultar
```

Depois de qualquer acao, atualize a lista e a contagem. `ocultar` deve remover
o item da tela quando `incluir_ocultas=false`.

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
