# Análise dos trials locais e continuidade do P0-D

> **English summary.** This analysis (2026-10-01, base `8fe0b92`) reviews the local trial evidence: nine v1 reports, five agent session directories and 52 P0-A journals. The six fixed v1 suite runs are internal smoke tests, not real tasks; the five sessions projected to v2 hold 123 bundles that all verify offline with `admit_read`, nine receipts record `deny/safe_open_failed`, coverage is unknown for sessions without journals, and `task_outcome` and all `durations_ms` stages remain `null`. The slice fixes a collector bug that counted intact journals from another `run_id` as invalid, and implements opt-in timing capture with `ADF_CAPTURE_TIMINGS=1` (step 3). The data supports no productivity, latency or total-coverage claim, the external trial (step 4) is skipped, and ADRs 0010–0012 remain Proposed. The full record below is in Portuguese.

Data: **2026-10-01**. Base: `8fe0b92`, branch `feat/p0d-session-collector`.
Modo: **Maintainer**. Evidência disponível: nove relatórios v1, cinco diretórios
de sessão do agente e 52 journals P0-A no clone local. Dados brutos permanecem
em `docs/observability/`, ignorados pelo Git. Este documento publica somente
contagens e reason codes; não copia IDs de sessões, paths, prompts ou conteúdo.
A atribuição das capturas ao Claude vem do relato do mantenedor; a versão do
agente não está registrada nesses artefatos.

## O que os testes demonstram

As seis execuções da suite fixa v1 são smoke tests internos, não tarefas reais.
Duas terminaram com cinco `workspace_worktree_prepare_failed` cada, sem bundle.
As outras quatro registram, cada uma, cinco tentativas e quatro bundles:
três válidos e um inválido. Os casos de binding mismatch fazem parte da suite
negativa; seu bundle inválido não deve ser convertido em decisão válida.
Os três relatórios de ingestão v1 reutilizam capturas locais: os dois últimos
contêm as mesmas contagens (20 bundles, 16 válidos, quatro inválidos). Não são
20 trials independentes e não devem ser somados como novas sessões.

Projeção v2 das cinco sessões, ordenadas pelo início das capturas disponíveis:

| Sessão anônima | Período UTC | Tentativas observadas | Bundles válidos | Receipts delivered | Receipts deny | Bundles órfãos | Cobertura |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| A | 2026-09-26 | 0 | 1 | 1 | 0 | 1 | unknown |
| B | 2026-09-26 | 0 | 1 | 1 | 0 | 1 | unknown |
| C | 2026-09-26 | 0 | 29 | 27 | 2 | 29 | unknown |
| D | 2026-09-27 a 2026-09-30 | 31 | 72 | 69 | 3 | 41 | observed |
| E | 2026-10-01 | 21 | 20 | 16 | 4 | 0 | observed |

Todos os 123 bundles das cinco sessões verificam offline; todos registram
`admit_read` no PDP. Nove receipts registram `deny/safe_open_failed`, distribuídos
em C (dois), D (três) e E (quatro). Admissão do PDP não garante entrega pelo
runtime. Os journals disponíveis são completos e verificam; não há duplicatas
ou conflitos de correlação nessas capturas. Ausência de journals em A/B/C
significa cobertura desconhecida. Os 41 órfãos de D indicam ausência de
correlação disponível, sem demonstrar perda de captura ou sua causa.

Em E, a tentativa adicional terminou em `invalid_referenced_contract`, sem
bundle. Portanto, há **21 tentativas**, **20 decisões verificadas**, **16 receipts
delivered** e **cinco términos deny**; nenhum desses números prova sucesso da
tarefa. `task_outcome` e todos os estágios de `durations_ms` permanecem `null`.
Não calcular produtividade, economia, latência zero ou cobertura total do
agente com esses dados. As rotas alternativas continuam fora do matcher;
hooks nativos continuam `gate_only`, conforme a matriz de cobertura.

## Problemas corrigidos nesta fatia

O coletor anterior classificava como inválido qualquer journal com outro
`run_id`. Como `_attempts` é compartilhado, E recebia 31 falsos inválidos e D
recebia 21. Agora, journals estrangeiros íntegros têm contador próprio; mudanças
de binding dentro do journal continuam inválidas. Duplicatas verificadas também
têm contadores próprios, sem aumentar denominadores. Cópias conflitantes do
mesmo journal invalidam a captura, evitando escolher um término por ordem de
arquivo. Decisões e receipts são agregados apenas de bundles distintos válidos.

Foram preservados os dois testes locais já existentes para conflitos de bundle
e FIFOs. O schema v2 ganhou campos opcionais com invariantes, exemplos válidos
e negativos e oráculo normativo; leitores atuais continuam verificando v2
antigo. Os contratos, arquivos e hashes v1 não mudaram. Novos relatórios locais
usam o trial `review-20261001`, sem reescrever relatórios anteriores.

## Continuidade após a análise

A etapa 3 foi implementada nesta branch após a análise acima. O host pode
ativar `ADF_CAPTURE_TIMINGS=1` para capturar os seis estágios com relógio
monotônico nos gates nativos e MCP, sem alterar contratos v1. O coletor
verifica as observações separadas e seus bindings antes de agregar tempos.
As capturas históricas da tabela continuam sem tempos ou resultado de tarefa.
Dez testes novos exercitam zero/ausência, falhas, interrupções, correlação e
captura opt-in; a validação final passou com 28 self-tests no `make quality`,
além de `make eval`, `make graph-check` e revisão de privacidade. Os skips
listados abaixo permanecem. A etapa 4 externa continua **skipped**.

## Próxima entrega, em ordem

1. **P0-D, etapa 3 em trabalho real:** exercer a instrumentação implementada
   com captura opt-in; registrar versão do agente e SHA. As medições locais
   sintéticas não substituem esse uso nem medem duração do modelo ou sessão.
2. **P0-C em produto:** validar instalação e entrega do MCP read-only em um
   cliente Claude/Codex real, registrando versão e tool. O teste do SDK não
   substitui essa evidência. ADRs 0010–0012 seguem Proposed até revisão humana.
3. **P0-D, etapa 4:** trial externo com SHA da revisão, versão do agente,
   tarefa e critério reproduzível de aceite; separar suite fixa e trabalho
   real. Registrar avaliação externa e baseline antes de comparar valor.
4. **Depois dos trials:** priorizar diagnóstico local de onboarding e H5 com
   contexto/proveniência. H3-02, novos efeitos, providers remotos e SaaS seguem
   sujeitos às decisões e evidências previstas no roadmap.

O trial externo desta fatia é **skipped**: as capturas disponíveis não fornecem
repositório externo com tarefa, versão e critério de aceite verificáveis. Esta
análise não aceita ADRs nem marca P0-D como Done em `main`.

## Validação desta fatia

- `hooks/test-session-trial.sh`: 11 testes passaram, incluindo as regressões
  preexistentes de referências conflitantes e FIFO e a invariância de ordem.
- `make quality`: quatro gates executados passaram e 27 self-tests passaram.
  A execução final foi autorizada fora do sandbox para criar worktrees em `.git`.
- `make eval`: `median-bug` e `sum-bug` passaram; `eval-required` passou.
- `make graph-check` e `git diff --check`: passaram; revisão adicional de
  código e privacidade sem achados.
- **Skipped:** cobertura JS (sem script), ciclos (sem madge), mutação (sem
  Stryker) e lint Python (Ruff indisponível no venv). O gate não detecta uma
  stack Python na raiz; os módulos foram exercitados pelos self-tests, sem
  claim de cobertura, complexidade ou mutação Python. Build/typecheck não
  estão configurados para esta fatia.

Referências locais: [spec P0-D](../../../docs/specs/p0d-trial-sessions.md),
[contrato v2](../../integration/v2/README.md), [guia de trials](../trials.md),
[matriz de cobertura](../integrations/coverage-2026-09-29.md) e
[roadmap](../roadmap.md).
