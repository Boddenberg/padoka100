# Relatorios inteligentes de Analytics

## Objetivo

Transformar o Resumo em uma central de inteligencia do negocio. O usuario solicita um
relatorio sem bloquear o aplicativo, acompanha o processamento, recebe um aviso quando o
resultado estiver pronto e pode abrir, compartilhar ou exportar o documento em PDF.

## Decisoes de produto

- Acesso: planos `analitico`, `ia` e `admin`, alem de `papel=administrador`.
- Frequencia: uma solicitacao a cada sete dias para contas comuns; administradores nao
  possuem limite. Uma solicitacao em andamento e reaproveitada em vez de duplicada.
- Periodo: o usuario escolhe de 1 a 366 dias, sem datas futuras. O padrao e 30 dias.
- Plano Analitico: indicadores, comparacoes, tendencias e recomendacoes deterministicas,
  sempre baseadas nos dados persistidos.
- Plano IA/Admin: todo o conteudo analitico mais uma leitura contextual estruturada pela IA.
  Se a IA estiver temporariamente indisponivel, o relatorio continua sendo entregue e a
  limitacao fica explicita.
- Exportacao: PDF profissional gerado a partir do snapshot imutavel do relatorio. Um token
  aleatorio e revogavel permite abrir e compartilhar o PDF sem expor a sessao do usuario.

## Arquitetura

1. `POST /analytics/relatorios` valida plano, periodo, limite e concorrencia.
2. A solicitacao e persistida em `analytics_relatorios` com status `na_fila`.
3. Um executor serial processa um relatorio por vez e devolve a resposta HTTP imediatamente.
4. O worker reivindica o job com update condicional, coleta os dados do usuario, calcula o
   periodo anterior equivalente, produz os insights e salva um snapshot JSON versionado.
5. Jobs pendentes sao retomados no startup; jobs presos em processamento por mais de trinta
   minutos voltam para a fila.
6. Ao concluir, o backend publica uma notificacao individual com a rota do relatorio.
7. O app consulta a lista em polling leve apenas enquanto houver jobs em andamento.
8. O PDF e montado sob demanda a partir do snapshot, garantindo que numeros e narrativa nao
   mudem depois da geracao.

## Conteudo calculado

- faturamento, custo, lucro, margem, numero de vendas, ticket medio e unidades vendidas;
- producao, eficiencia de venda, sobras, descarte e reaproveitamento;
- comparacao com periodo anterior equivalente e variacoes percentuais;
- serie diaria, melhor e pior dia, desempenho por dia da semana e faixas de horario;
- ranking de produtos, participacao no faturamento, margem, esgotamentos e sobras;
- oportunidades, alertas, destaques e qualidade/completude dos dados;
- interpretacao contextual, acoes recomendadas e pontos de atencao para plano IA/Admin.

## Seguranca e resiliencia

- Toda coleta parte de `usuario_id`; tabelas filhas sao acessadas apenas por ids dos pais ja
  filtrados.
- O backend e a fonte de verdade para plano, cooldown e propriedade do relatorio.
- Um indice parcial impede dois jobs ativos por usuario mesmo com requisicoes simultaneas.
- Falha de IA nao descarta os calculos; falha total marca o job como `falhou` e libera nova
  tentativa.
- O executor tem concorrencia um, evitando rajadas contra Supabase e OpenAI.
- O token de exportacao e UUID aleatorio e pode ser trocado sem alterar o relatorio.

## Validacao

- testes puros dos calculos e recomendacoes;
- testes de integracao de acesso, cooldown, propriedade, processamento e notificacao;
- validacao de lint/typecheck/build web;
- geracao de PDF de amostra, renderizacao para PNG e inspecao visual;
- revisao da tela em preview web responsivo antes da publicacao no canal EAS `preview`.
