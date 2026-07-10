# Planos de acesso

## Objetivo

O controle de acesso do backend separa autenticacao de autorizacao:

- autenticacao confirma quem e o usuario, usando o fluxo Supabase ja integrado;
- autorizacao decide o que o usuario pode fazer, usando o campo `usuarios.plano` e uma matriz de capacidades.

O modelo atual considera apenas usuarios individuais donos de padarias. Nao ha grupos, empresas ou times nesta fase.

## Planos

| Plano | Uso esperado | Capacidades principais |
| --- | --- | --- |
| `basico` | Operacao diaria da padaria | catalogo, locais, dia de venda, vendas, relatorios basicos, midia e perfil |
| `analitico` | Gestao com leitura de historico e custos | tudo do basico, relatorios avancados, historico, compras e custos |
| `ia` | Operacao assistida por IA | tudo do analitico, comandos de IA, analise de IA e assistente de custeio |
| `admin` | Administracao da plataforma | tudo do plano IA, admin, notificacoes admin, RAG e seed |

## Arquitetura

A matriz central fica em `app/modules/auth/capacidades.py`.

O servico de autenticacao sempre devolve `plano` e `capacidades` em `UsuarioSaida`. Isso permite que o app esconda entradas de features sem duplicar regra critica de seguranca.

Rotas protegidas usam `exigir_capacidade("capacidade")`. A dependencia valida o usuario autenticado e retorna:

- `401` quando nao ha sessao valida;
- `403` com `feature_not_available` quando o usuario existe, mas o plano nao libera a capacidade.

Chamadas com `X-API-Key` continuam liberadas para integracoes internas e operacionais ja existentes.

## Decisoes

- `papel=dono` nao equivale a admin. O primeiro usuario pode ser dono da padaria e continuar no plano `basico`.
- O plano `admin` ou `papel=administrador` libera as capacidades administrativas.
- O frontend usa as capacidades apenas como experiencia de produto. O backend e a fonte de verdade.
- Planos desconhecidos caem para `basico`, evitando liberar acesso por erro de dado.
- A evolucao recomendada para billing e assinatura e atualizar apenas `usuarios.plano`, mantendo a matriz de capacidades estavel.

## Migracao

A migracao `supabase/migrations/013_planos_acesso.sql` adiciona `usuarios.plano` com default `basico`, restricao de valores permitidos e indice para consultas administrativas.

## Operacao

Administradores reais podem alterar o plano de um usuario pelo endpoint `PATCH /api/v1/auth/usuarios/{usuario_id}/plano`.

O primeiro usuario continua sendo criado como `papel=dono` e `plano=basico`. Para liberar administracao da plataforma, atualize o usuario para `plano=admin` ou `papel=administrador` usando credenciais administrativas.

## Manutencao

Para criar uma nova feature paga:

1. Adicione uma capacidade em `app/modules/auth/capacidades.py`.
2. Inclua a capacidade no plano minimo esperado.
3. Proteja a rota com `exigir_capacidade`.
4. Exponha a feature no frontend usando `capacidades` do usuario.
5. Adicione teste cobrindo o plano que libera e o plano que bloqueia.
