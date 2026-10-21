# Roadmap

Atualizado: 2026-10-16 · Versão: 0.1.0 (experimental)

> **Produto:** posicionamento, Now/Next/Later/Not doing e pacotes de trabalho estão em
> [`docs/product/ROADMAP.md`](../../docs/product/ROADMAP.md) e no
> [plano de implementação](../../docs/product/IMPLEMENTATION_PLAN.md). Este arquivo é o histórico de engenharia.

Este roadmap tem duas partes. A primeira é o plano vigente do **Agent Development Harness**
(fatias H1–H7, Spec aprovada em 2026-09-17, ADRs 0005–0009). A segunda preserva o roadmap
histórico do harness (Fases 0–5, 2026-07-08) com o estado de cada item, porque boa parte dele
foi entregue e continua sendo a base de adoção.

Regras: nada aqui contradiz um ADR `Accepted`. Um item só muda para **Done** quando está em
`main` com testes. **Blocked** significa que exige ADR próprio ou evidência que ainda não existe.

Pesquisa complementar: [evolução do ADF, Jev e próximas implementações (2026-09-26)](research/2026-09-26-product-evolution.md).
É uma proposta para revisão, com fontes recentes, lacunas verificadas, fatias de implementação
e critérios de produto; não altera os aceites ou a autorização do Plano H abaixo.

P0-A (journal), P0-B (policy do host) e P0-C (MCP stdio) entraram em `main`
pelos PRs #47 e #48. Os ADRs [0010](architecture-decision-records/0010-adapter-attempt-lifecycle.md),
[0011](architecture-decision-records/0011-pinned-host-read-policy.md) e
[0012](architecture-decision-records/0012-mediated-stdio-read.md) continuam
Proposed até revisão humana; integração MCP em clientes Claude/Codex reais
continua sem validação. A próxima fatia é [P0-D: sessões e medições de trial](../../docs/specs/p0d-trial-sessions.md).

P0-D, etapas 1–3, entrou em `main` pelo PR #51: coletor de sessão, schema
fechado, verificador, exemplos e oráculo; contagens separadas para journals
de outras sessões, duplicatas e decisões de bundles verificados.
A etapa 4 continua pendente; P0-D completo não é **Done**.
A [análise das capturas de 2026-10-01](research/2026-10-01-trial-analysis.md)
expõe os denominadores e limites dos testes. A etapa 3 agora inclui captura
opt-in de tempos monotônicos por tentativa, separada de v1, e agregação com
proveniência no v2. Resta o trial externo com critério reproduzível de sucesso
da tarefa e a validação MCP em produto. A [revisão de 2026-10-04](research/2026-10-04-trial-readiness.md)
confirma os agregados locais e descreve a proveniência opcional entregue
no PR #52 (development repository), integrado
em `main`. O PR inclui o contrato separado de avaliação
externa e os gates portáteis. As evidências de pesquisa e este roadmap estão
no PR #53 (development repository), mesclado
na branch de implementação após a integração do PR #52. A entrega documental
segue em um PR próprio para `main`, preservando o limite de 30 arquivos.

**Borda A2A e observabilidade (2026-10-14 → 2026-10-16).** A2A-1 a A2A-8a entraram em `main`
(PRs #55–#62), com os ADRs [0013](architecture-decision-records/0013-a2a-edge-authn-authz.md)–[0019](architecture-decision-records/0019-a2a-token-exchange-seam.md)
**Accepted**. O export OTel redigido ([ADR 0020](architecture-decision-records/0020-control-plane-otel-export.md), #64–#66)
e o primeiro [trial A2A ao vivo](observability/trials/a2a-live/README.md) (#67–#68) também estão em `main`.

## Parte 1 · Plano H (control plane)

Referência: [Spec H0–H7](../../docs/specs/agent-development-harness.md) e ADRs
[0005](architecture-decision-records/0005-agent-development-harness.md),
[0006](architecture-decision-records/0006-mode-and-run-config-resolution.md),
[0007](architecture-decision-records/0007-runtime-and-tool-policy-boundary.md),
[0008](architecture-decision-records/0008-pep-and-constrained-local-read-runtime.md),
[0009](architecture-decision-records/0009-local-control-plane-evidence-integration.md).

### Entregue

| Fatia | Entrega | Código | Validação |
| --- | --- | --- | --- |
| H1-01 | `RunEvent` + `GateResult` opt-in em um gate real, compatibilidade com JSONL/CSV legados | `hooks/run-events.py`, `contracts/v1` | `hooks/test-run-events.sh` |
| H1-02 | Sete contratos v1 + oráculo normativo + matriz de validação | `contracts/v1` | `hooks/test-contracts-v1.sh` |
| H2-01 | Resolução pura de `Mode` + `RunConfig` (`ResolutionRequest` → `ResolvedRunConfig`) | `modes/resolver.py`, `modes/v1` | `hooks/test-mode-resolution.sh` |
| H2-02 | Registry + PDP puro: `ToolProfile`, `ToolCallIntent`, `PolicyBundle`, `PolicyContext`, `AdmissionDecision`; só `admit_read` | `tools/pdp.py`, `tools/v1` | `hooks/test-tool-admission.sh` |
| H3-01 | PEP, `LocalReadRuntime` por handle, `WorkspaceManager`, `RuntimeWorkspaceDescriptor`, `ReadResult` tainted, receipt redigido, `sensitive_path_policy_v1` | `runtime/*`, `runtime/v1` | `hooks/test-runtime-read.sh` |
| H4-01 | `AdapterRequest`, `EvidenceBundle`, `compose`, `verify_offline`, `logical_replay` | `integration/local_evidence_bundle.py`, `integration/v1` | `hooks/test-local-evidence-bundle.sh` |
| H4-01b | Métricas agregadas de trial com invariantes e `report_sha256` | `integration/evidence_trial_metrics.py` | `hooks/test-evidence-trial-metrics.sh` |
| H4-01c | Pilot local isolado: três trials sobre revisões internas, só agregado publicado | `hooks/run-local-evidence-pilot.py` | `make local-evidence-pilot`, `hooks/test-local-evidence-pilot.sh` |
| H4-02 | Modo check sem escrita (`ADF_EVAL_WRITE=0`): `make eval-check`, `make quality-check`; fail-closed `eval_persistence_disabled` sob `ADF_EVENTS_V1=1` | `Makefile`, `hooks/eval-*.sh` | `hooks/test-eval-check-mode.sh` |

### Entregue · borda A2A e observabilidade

| Fatia | Entrega | ADR | Validação |
| --- | --- | --- | --- |
| A2A-1/2 | Agent Card fechado, AuthN bearer, scope por skill no PDP | [0013](architecture-decision-records/0013-a2a-edge-authn-authz.md) | `hooks/test-a2a-gateway.sh` |
| A2A-3 | `CallerPrincipal`, enforcement no PEP, `A2AEvidenceRecord` + `verify_record` | [0014](architecture-decision-records/0014-caller-principal-envelope.md) | idem |
| A2A-4 | Cadeia de delegação `act` validada, teto de scopes delegados | [0015](architecture-decision-records/0015-a2a-delegation-chain.md) | idem |
| A2A-5 | Task `auth-required` retomável | [0016](architecture-decision-records/0016-a2a-auth-required-task.md) | idem |
| A2A · RS256 | RS256 com JWKS pinada por SHA-256 | [0017](architecture-decision-records/0017-a2a-rs256-pinned-jwks.md) | idem (mutação + oráculo `openssl`) |
| A2A-6 | Pausa `input-required` com confirmação humana direta | [0018](architecture-decision-records/0018-a2a-input-required-confirmation.md) | idem |
| A2A-6b | `effect_binding` nos records de pausa, retomada e deny de retomada (aprovação ligada ao efeito) | [0022](architecture-decision-records/0022-a2a-effect-bound-confirmation.md) | idem |
| MP-04 | Principal local derivado do harness (`agent_type`) no journal e no span | [0023](architecture-decision-records/0023-local-principal-from-host-harness.md) | `hooks/test-local-edge-otel.sh` |
| A2A-7 | Regras do seam de Token Exchange; endpoint adiado | [0019](architecture-decision-records/0019-a2a-token-exchange-seam.md) | idem (test double) |
| A2A-8a | TLS terminado por proxy do host na frente do loopback | — (doc) | `make_server` recusa bind não-loopback |
| MP-05 | `principal_rules` na policy pinada: least privilege por agente decidido pelo PDP | [0024](architecture-decision-records/0024-principal-rules-in-pinned-policy.md) | `hooks/test-principal-policy.sh` |
| OBS-1 | Span OTel redigido por request A2A, opt-in, fail open/closed; sink Jaeger ou Langfuse (headers OTLP) | [0020](architecture-decision-records/0020-control-plane-otel-export.md) | `hooks/test-otel-export.sh` |
| CLI | Comando único `adf` (projects, hook, hook-snippet, policy, a2a, verify, version) sobre os scripts existentes | [0025](architecture-decision-records/0025-adf-operator-cli.md) | `hooks/test-adf-cli.sh`, `hooks/test-packaging.sh` |
| TRIAL-A2A | Trial ao vivo T1–T7, prints do Jaeger, benchmark OTel on/off | — | [relatório](observability/trials/a2a-live/README.md) |

### Próximo (ordem recomendada)

1. **Concluir P0-D.** Exercitar a captura opt-in dos seis estágios em trabalho
   real, com versão do agente, SHA, tarefa e critério de aceite externos.
   Instrumentação e testes locais estão em `main`; ausências permanecem `null`.
2. **Validar MCP em cliente real.** Gates Claude/Codex e MCP stdio já existem;
   identidade dos bytes foi testada com cliente SDK, sem validação em produto.
   Não ampliar claims além da [matriz de cobertura](integrations/coverage-2026-09-29.md).
3. **Trials com design partners.** O runner existe (`make local-evidence-trial`, P2): suite fixa
   sobre o adapter ou ingestão dos bundles do gate `Read`, agregados via H4-01b. Falta o dado
   externo com tarefa avaliada. Capturas locais de sessões já existem, sem
   baseline ou critério de sucesso. Sem esses dados, nenhuma alegação de valor
   além de "evidência técnica".
4. **Trial A2A reproduzível e completo.** Levar o harness do trial para `make a2a-live-trial`
   (com teste/eval); agregador que entenda `_a2a/` (hoje `local-evidence-trial` conta records
   como bundles inválidos); rodada com RS256/JWKS de IdP real e com Langfuse ao vivo.
5. **Higiene.** `docs/evals/results.csv` não deve mudar em PRs documentais (já coberto por
   `make quality-check`); completar cobertura de `skipped` por plataforma (socket, device).

### Bloqueado

| Item | Bloqueio |
| --- | --- |
| H3-02 · isolamento/runtime adicional (processo, host, Docker) | ADR próprio + evidência de uso do H3-01. ADR 0009 mantém H3-02 bloqueado. |
| `write`, `network`, `secrets`, `destructive` | ADR próprio com idempotency key, preflight impact binding, aprovação humana vinculada e expirada, egress deny-by-default. |
| MCP com novos efeitos ou transportes | P0-C oferece apenas read-only por stdio, com PDP/PEP existentes e ADR 0012 Proposed. Novos efeitos/transportes exigem ADR próprio. |
| A2A-8b · DPoP/mTLS (token ligado ao remetente) | ADR próprio; hoje um token roubado vale até `exp` (≤ 1 h). |
| A2A-9 · Agent Card assinado | ADR próprio. |
| Endpoint de Token Exchange (RFC 8693) | ADR 0019: *won't do yet*; derivação cabe a um AS confiável. |
| Spans do gate local (`local_read`) | ADR 0020 cobre só a borda A2A; ampliar exige demanda de design partner. |
| Publicação npm / PyPI | Não autorizada (ADR 0008). Exige conta do mantenedor, 2FA, CI e ADR aceito antes de expor enforcement. |
| Decision Model tipado / Jev / Laya | Só após suite de trials separada com grader determinístico e revisão de falso allow/deny (ADR 0007). |
| SaaS, SSO/RBAC, dashboard, cobrança | Decisão comercial futura, fora de H4. A licença vigente é MIT. |

### Planejado (sem data)

| Fatia | Objetivo | Condição |
| --- | --- | --- |
| H5 | Contexto com hash e proveniência (grafo fresco como insumo do Harness, não do PEP) | após adapter e trials |
| H6 | Aprovação e review por risco; `approval_required` passa a ser emitido; migração da política de reviewers | ADR próprio; nenhum reviewer é removido antes |
| H7 | Learning controlado sobre traces e evals | continua suggest-only; alteração estrutural só por PR humana |

## Parte 2 · Histórico do harness (Fases 0–5, 2026-07-08)

Diagnóstico à época: o projeto tinha tese clara (contexto controlado, verificação executável,
review por métricas, economia de tokens) mas gates que existiam só como contrato em docs.
Estado atual de cada fase:

| Fase | Objetivo | Estado |
| --- | --- | --- |
| 0 · Estabilizar o contrato | `make quality` real por stack, `make graph-check`, `docs/metrics/history.csv`, README honesto | **Done** |
| 1 · Observabilidade e evidência | `make metrics-snapshot`, `make rtk-report`, `make graph-hit-rate`, PR template | **Done** |
| 2 · Skill governance | `make skill-audit`, metadata por skill, política de depreciação | **Done** (`docs/skill-governance.md`) |
| 3 · MCP seguro | `mcp/servers.json`, `make mcp-audit`, threat model | **Done como controle estático**; não é autorização nem executor |
| 4 · Agent improvement loop | `docs/evals/`, `make eval`, `docs/traces/`, `make learn` suggest-only | **Done** (ADR 0004) |
| 5 · Produto e distribuição | CLI `adf doctor`, releases versionadas, exemplos completos, docs de migração | **Parcial**: `VERSION` 0.1.0 e `make install-into` existem; CLI e releases não. Superfície pública agora depende do Plano H (ADR 0008). |

### Princípios que continuam valendo

1. Fechar o ciclo primeiro: todo comando importante produz sinal verificável.
2. Medir antes de automatizar.
3. Skills poucas e especializadas.
4. MCP com segurança por padrão; inventário e allowlist são pré-requisito, não autorização.
5. Um core, adaptadores finos.

### Referências externas (mantidas)

- Anthropic, [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents).
- Anthropic, [How we contain Claude across products](https://www.anthropic.com/engineering/how-we-contain-claude).
- Anthropic, [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).
- Model Context Protocol, [Tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
- OpenAI, [Harness engineering](https://openai.com/index/harness-engineering/) e [Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/).
- Zou et al., [Security Challenges in AI Agent Deployment](https://arxiv.org/abs/2507.20526).
- SWE-bench ([arxiv](https://arxiv.org/abs/2310.06770)) e SWE-Skills-Bench ([arxiv](https://arxiv.org/abs/2603.15401)).
- Segurança MCP: [arxiv 2506.13538](https://arxiv.org/abs/2506.13538), [arxiv 2504.03767](https://arxiv.org/abs/2504.03767).

## Riscos

- Automação antes de verificação: parecer mais avançado com menos confiança.
- Chamar checagem de path em userspace de "sandbox": promessa de segurança falsa.
- Claims não medidos: percentuais de vendor (Ponytail, RTK) só entram como metas rotuladas até
  haver medição local.
- Ampliar efeito (write, rede) por conveniência antes do PEP/Runtime correspondente.
