# P0-D · Sessões e medições de trial

> **English summary.** This spec defines P0-D, a separate versioned session report for trials, because the H4-01b v1 report derives one `trial_id` per bundle and fills unmeasured `decision_latency_ms` with zero. It fixes the identifiers (`trial_id`, `task_id`, `session_id`, `attempt_id`, `bundle_id`) and denominators, keeps `task_outcome` `null` until an external evaluator records it, and requires monotonic durations for six stages outside PDP/PEP, where `null` means not observed and `0` means a real measurement below millisecond resolution. Status: Approved by PR #50 on 2026-09-29, delivered in four incremental steps ending with a real external trial; an unavailable external trial is `skipped`, never a positive result, and v1 contracts and reports stay unchanged. The full record below is in Portuguese.

- **Status:** Approved by PR #50 · 2026-09-29
- **Origem:** [plano de evolução](../../ai-development-framework/docs/research/2026-09-26-product-evolution.md#p0-d--métricas-sem-ambiguidades-e-primeiro-trial-externo).
- **Dependências:** P0-A, P0-B e P0-C integrados em `main`.

## Problema

O relatório H4-01b v1 conta um `trial_id` derivado de cada bundle, embora um trial
real contenha sessões e várias tentativas. Na ingestão de bundles, preenche
`decision_latency_ms` com zero quando o tempo não foi medido. O indicador
`source.latency_recorded=false` esclarece a origem, mas o número continua
ambíguo para leitores que usam apenas o campo numérico. Bundles tampouco
registram tentativas sem evidência ou o resultado da tarefa do agente.

## Contrato a implementar

Criar um **formato separado e versionado** para o relatório de sessão P0-D.
Não alterar contratos, hashes, arquivos ou leitores H4-01b v1. O relatório
novo referencia evidência v1 por identificador e resultado de verificação;
jamais a usa como autorização, nem copia conteúdo lido, prompt ou path físico.

| Identificador | Cardinalidade | Origem |
| --- | --- | --- |
| `trial_id` | Um experimento comparável; pode conter várias sessões | Host |
| `task_id` | Uma tarefa definida por critério externo de aceite | Host |
| `session_id` | Uma execução do agente; único dentro do trial e igual ao `run_id` observado | Host |
| `attempt_id` | Uma tentativa de read observada no journal P0-A | Journal verificado |
| `bundle_id` | Zero ou um bundle correlacionado a uma tentativa | Bundle verificado |

O denominador de **tentativas observadas** é o número de eventos `started`
distintos que verificam. `complete`, `incomplete` e `invalid` são estados de
captura, não resultados de tarefa. Um journal incompleto conta como tentativa
observada, com término desconhecido. Um bundle sem journal correlacionável
conta como bundle órfão; não inventar tentativa. Duplicatas, mudanças de
`session_id`/`run_id`, referências conflitantes e artefatos inválidos são
contados separadamente, sem entrar em numeradores de sucesso. Vários bundles
em uma sessão são esperados; não representam vários trials. Ausência de
journal significa **cobertura desconhecida**, não zero tentativas.

`task_outcome` permanece `null` até um avaliador externo registrar, com
critério de aceite e teste reproduzível, `success`, `failure` ou `skipped`.
Receipt `delivered`, journal `complete` e resposta MCP recebida não provam
sucesso da tarefa nem consumo pelo modelo. Agregar decisões somente de
bundles que passam pelo verificador v1, sem usar `trial_count` v1 como
denominador de sessões.

## Tempo e proveniência

Registrar durações **fora do PDP/PEP e contratos puros**, com relógio
monotônico, para `prepare` (worktree), `decision` (PDP), `read` (runtime),
`persistence` (writes de journal e bundle), `cleanup` (worktree) e `total`
(entrada até retorno do adapter). Um estágio não executado fica ausente;
spans de persistência podem ser somados apenas dentro desse estágio. Tempos
aninhados não devem ser somados para fabricar o total. Cada duração tem
unidade `ms`, inteiro não negativo ou `null` quando não foi observada.
`0` significa medição real abaixo da resolução em milissegundos; nunca
significa ausente. Timestamps de parede servem somente à ordenação e não
calculam latência. Ingestão de bundles/journals antigos deixa tempos `null`.
Não inferir percentis de uma amostra sem contagem e proveniência explícitas.

## Aceite e entrega incremental

1. Especificar schema fechado, exemplos válidos/inválidos e verificador do
   novo relatório. Testar `null` versus zero, duplicatas, hashes e bindings.
2. Coletar tentativas e bundles de uma pasta de sessão **encerrada**; não
   seguir symlinks, expor paths/conteúdo ou executar PDP/PEP na agregação.
3. Instrumentar os seis estágios na borda do adapter, sem mudar evidência
   v1, decisão ou conteúdo entregue; testar relógio monotônico e falhas.
4. Executar um trial em repositório externo e tarefa reais, separado da
   suite fixa, com revisão humana dos artefatos compartilháveis. Registrar
   versão do agente, SHA da revisão e critério de sucesso sem PII.

Gates por fatia: testes de contrato e falhas, `make quality`, `make eval`,
`make graph-check` e revisão de privacidade. Um trial externo indisponível é
**skipped**, nunca resultado positivo. A reversão desativa somente o coletor
novo; relatórios v1 permanecem legíveis e não são reescritos.
