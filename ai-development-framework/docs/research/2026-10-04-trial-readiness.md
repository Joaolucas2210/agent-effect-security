# Dados coletados e preparação do próximo trial

> **English summary.** This record (2026-10-04, base `1a2d7ce`, `main`, PR #51) reviews the collected trial data and prepares the next trial. The five local v2 reports verify and total 52 observed attempts and 123 valid bundles, but they are projections of five historical sessions without task outcome or complete provenance, and the `make metrics` counts describe harness-recorded work, not external task success. The collector now accepts optional provenance with four closed fields (agent, version, full Git SHA and SHA-256 of the acceptance document), included in the report hash; these are host declarations, not attestations, and `task_outcome` stays `null`. The change is in the working tree, not a new delivery on `main`, and the external trial remains skipped because no repository, task and verifiable acceptance criterion were selected. The full record below is in Portuguese.

Data: **2026-10-04**. Base: `1a2d7ce`, `main` (PR #51).
Modo: **Maintainer → Builder**. Consulta Graphify localizou o coletor,
verificador, schema e testes P0-D antes da análise de implementação.

## Evidência disponível

A leitura dos cinco relatórios v2 locais confirmou que todos verificam pelo
verificador atual. Somam 52 tentativas observadas e 123 bundles válidos.
São projeções das cinco sessões históricas, não novos trials independentes.
Nenhum registra resultado de tarefa ou proveniência completa do agente,
revisão e critério de aceite. A análise de 01/10 continua sendo a referência
para os denominadores, receipts e limites das capturas originais.

`make metrics` informou 114 eventos, 81 outcomes success, 11 failure e três
switches antes desta intervenção. Os 18 registros de eval passaram em dois
casos sintéticos. Esses números descrevem o trabalho registrado pelo harness;
não medem sucesso de tarefas externas, produtividade ou ausência de bypass.
Tokens e custo continuam `na`. Dados brutos e identificadores de sessão não
são publicados nesta revisão.

## Implementação desta continuidade

A spec P0-D aprovada exige versão do agente, revisão e critério reproduzível
de sucesso para a etapa externa. O coletor agora aceita proveniência opcional
com quatro campos fechados: agente, versão, SHA Git completo e hash SHA-256
do documento de aceite ou teste mantido pelo avaliador. A proveniência entra
no hash do relatório; preenchimento parcial ou inválido impede persistência.
Relatórios antigos continuam válidos, sem reescrita. O runtime, PDP/PEP e
contratos v1 permanecem intactos.

São declarações do host, não atestações nem execução de um avaliador.
`task_outcome` permanece `null`. O host deve definir o critério antes da tarefa,
reter seus bytes e revisar os metadados antes de compartilhar o relatório.
Esta implementação está no working tree e não representa nova entrega em `main`.

## Próximo passo

O trial externo continua **skipped** nesta revisão: falta selecionar repositório,
tarefa e critério de aceite verificável. Em seguida, registrar a versão real
do cliente e o SHA preparado pelo host, habilitar timings antes da sessão,
executar a tarefa e agregar a pasta encerrada com proveniência completa.
A avaliação externa deve ser registrada separadamente; este coletor ainda
não admite outcomes avaliados. Validar MCP em cliente real continua pendente.

## Validação

- Teste primeiro: os dois novos casos falharam antes da implementação.
  A suite final do coletor passou com 13 testes, incluindo compatibilidade,
  adulteração do digest, metadados inválidos e persistência via CLI.
- `make quality`: 28 self-tests e quatro gates executados passaram. A execução
  direta no sandbox falhou ao preparar worktrees; a repetição autorizada fora
  dele passou. `make eval`: dois casos e `eval-required` passaram.
- `make graph-check` e `git diff --check` passaram. A checagem do grafo compara
  com `HEAD`; não representa reindexação das alterações locais desta entrega.
- Evals rodaram com `ADF_EVAL_WRITE=0`, preservando os resultados históricos.
  Revisão do diff: sem novo conteúdo lido, prompt, path físico ou credenciais
  nos relatórios; sem mudanças na autorização ou novos efeitos.
- **Skipped:** cobertura JS (sem script), ciclos (sem Madge), mutação (sem
  Stryker), lint Python (Ruff ausente no venv) e uma validação independente
  opcional de JSON Schema no self-test de run events. Os contratos P0-D foram
  exercitados com jsonschema pinado. A stack Python não é detectada na raiz;
  não há claim de cobertura, complexidade ou mutação Python. Build/typecheck
  não estão configurados para esta fatia. Trial externo e MCP em produto
  continuam pendentes.

Referências: [spec P0-D](../../../docs/specs/p0d-trial-sessions.md),
[análise histórica](2026-10-01-trial-analysis.md),
[guia de captura](../trials.md#registrar-proveniência-do-trial).
