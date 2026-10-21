# Validação do ADF instalado no project-b

> **English summary.** This record (2026-10-04) validates ADF installed in the external repository `project-b` at a pinned revision. The existing data there were fixed-suite negative cases, not real agent sessions; a defect in which v1 ingestion counted a `_timings` JSON file as an invalid bundle was reproduced and fixed, and a direct host probe (`other/host-probe-1.0`) produced four attempts, three valid bundles and four correlated monotonic observations. The portable `make -f Makefile.adf quality` gate failed in the target because the Codex self-test depends on a host `.codex/hooks.json`, while `make -f Makefile.adf eval` passed. The probe is a host integration rehearsal, not a real Claude/Codex client or agent task result: `task_outcome` stays `null` and step 4 of the P0-D spec is not completed. The full record below is in Portuguese.

Data: **2026-10-04**. ADF base: `1a2d7ce` com mudanças locais de proveniência
e correção de ingestão. Repositório externo: `project-b`, revisão
`ca5239cd7010dab86a38d17ead79414fd43f8c3d`. Modo: **Maintainer → Builder**.

## Classificação dos dados existentes

O destino tinha um relatório v1 com `source.kind=fixed_suite`: cinco tentativas,
quatro bundles, uma entrega e quatro negações esperadas. Os cinco journals
estavam completos; três bundles verificaram e um era inválido por binding
mismatch intencional. Esses são casos da suite negativa, não falhas novas da
aplicação nem sessões reais do agente. Não havia relatórios v2 ou timings.

Não foi localizado arquivo local `.codex/hooks.json` nem settings Claude no
destino. O processo desta verificação não tinha configuração ADF apontando
para o destino. Isso não verifica a configuração global ou de outra sessão
do mantenedor; nas pastas inspecionadas só havia capturas da suite fixa.

## Defeito reproduzido e corrigido

Ao habilitar timings no teste portátil, a ingestão v1 incluiu um JSON de
`_timings` como bundle inválido: contou dois arquivos onde havia um bundle.
O runner agora exclui apenas os diretórios reservados `_timings`; artefatos
inválidos fora deles continuam contados. Contratos e hashes v1 não mudaram.
Relatórios anteriores permanecem intactos. A regressão do runner cobre um
arquivo inválido em `_timings`; o teste instalado cobre uma observação real,
proveniência completa, rejeição de preenchimento parcial e verificação v2
usando os módulos copiados, sem importar o clone de origem.

O core instalado recebeu atualização seletiva dos arquivos revisados, com
backup local. Antes da cópia, todos os arquivos existentes correspondiam ao
baseline de `HEAD`; nenhuma customização foi sobrescrita. Os 13 arquivos
de observabilidade preexistentes foram preservados por comparação de hashes.

## Captura instrumentada no repositório externo

Um ensaio direto do adapter, em pasta nova, produziu quatro tentativas,
três bundles válidos e quatro observações monotônicas correlacionadas.
Duas entregas coincidiram com os bytes do commit fixado; traversal e path
sensível foram negados. Não houve journal ou bundle inválido, órfão ou conflito.
A ingestão v1 contou apenas os três bundles, sem incorporar timings.
O relatório v2 verifica e contém proveniência e hash do critério de aceite,
retido separadamente em arquivo local com permissões restritas.

O produtor está identificado como `other/host-probe-1.0`. É um ensaio de
integração do host, não um cliente Claude/Codex real nem resultado de tarefa
do agente. `task_outcome` continua `null`; a duração do adapter não é duração
do modelo ou da sessão. Evidências brutas continuam locais e ignoradas pelo Git.

## Validação

- Aplicação: 71 testes SaaS/PostgreSQL passaram no banco isolado de teste;
  46 testes dos quatro scripts do piloto passaram; 11 testes Playwright com
  APIs simuladas passaram. Ruff da aplicação, teste de exportação e build
  TypeScript/Vite passaram. A primeira execução sem URL de teste teve 35 skips;
  a repetição com PostgreSQL isolado executou os 71 testes.
- ADF de origem: quatro testes do instalador, quatro do runner e 13 do coletor
  passaram; `make quality` passou com 28 self-tests e quatro gates;
  `make eval`, `eval-required`, `make graph-check` e diff check passaram.
- **Failed no destino:** `make -f Makefile.adf quality` parou no self-test
  Codex, que depende de `.codex/hooks.json` no host. O instalador não cria
  configuração de agente por contrato. O gate completo portátil não é verde;
  requer uma fatia própria que separe testes de pacote e checks de deployment.
  `make -f Makefile.adf eval` passou, sem histórico de resultados persistidos.
- Ruff adicional nos três arquivos ADF desta fatia encontrou 20 avisos
  preexistentes e nenhum aviso adicional comparado ao baseline; não é lint
  verde desses arquivos. A configuração mais estrita do destino não é um
  gate configurado no clone ADF.
- **Skipped no clone ADF:** cobertura JS, ciclos Madge, mutação Stryker e uma
  validação independente opcional de JSON Schema. Sem claim de cobertura ou
  mutação Python do ADF. MCP em produto, captura real do agente, teste OIDC
  local sem interceptação e avaliação de tarefa não foram executados nesta
  intervenção.

## Continuidade

1. Separar os self-tests portáteis das checagens de deployment, mantendo skips
   explícitos para configuração do host não instalada; não criar hooks por
   conveniência para fazer um gate passar.
2. Configurar e confiar a captura no cliente real usado pelo mantenedor,
   com pasta exclusiva, versão real, SHA e critério previamente definido.
3. Executar uma tarefa no destino e registrar avaliação externa reproduzível;
   o ensaio do host não conclui a etapa 4 da spec P0-D.

Referências: [spec P0-D](../../../docs/specs/p0d-trial-sessions.md),
[guia de trials](../trials.md), [roadmap](../roadmap.md).
