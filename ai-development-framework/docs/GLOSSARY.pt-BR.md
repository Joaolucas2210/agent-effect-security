# Glossário

[English](GLOSSARY.md) · **Português (Brasil)**

Termos com o nome exato usado no código e nos ADRs. Caminhos relativos a `ai-development-framework/`.

| Termo | Significado | Onde |
| --- | --- | --- |
| **ADF** | Agent Development Framework: control plane local-first para coding agents + harness de adoção no mesmo monorepo. | raiz |
| **Harness** | Camada de adoção e contexto: skills, commands, hooks, gates, evals, Graphify, RTK. Prepara intents e workspaces; não faz enforcement. | `skills/`, `commands/`, `hooks/` |
| **Adapter** | Componente local que compõe um `AdapterRequest` (intent, perfis, policy, contexto, descriptor) a partir de uma chamada do coding agent. Declarativo; não decide nem executa. | `integration/v1/schemas/adapter-request.schema.json` |
| **Registry** | Catálogo local, fechado e versionado de `ToolProfile`. Correspondência é exata por `tool_id` + `profile_sha256`. | `tools/v1` |
| **ToolProfile** | Interpretação controlada pelo ADF de uma ferramenta: operações, `effect_classes`, `resource_kind`, `supported_scopes`, `max_risk`, `profile_sha256`. Não é permissão. | `tools/v1/schemas/tool-profile.schema.json` |
| **effect class** | `read`, `write`, `network`, `secrets`, `destructive`. No v1 só `read` pode ser admitido. | ADR 0007 |
| **ToolCallIntent** | Intenção de chamada, não execução: `tool_ref`, `operation_id`, `arguments`, `resource_scope`, `run_id`, `task_ref`, `requested_budget`, `policy_context_ref`. | `tools/v1/schemas/tool-call-intent.schema.json` |
| **PolicyBundle** | Regras versionadas e hashadas (`policy_sha256`) com allowlists declarativas. Só restringe. | `tools/v1/schemas/policy-bundle.schema.json` |
| **PolicyContext** | Referências a policy, `ResolvedRunConfig`, restrições org/repo/mode e `runtime_capability` declarada. Capability ausente é "não demonstrada", nunca concedida. | `tools/v1/schemas/policy-context.schema.json` |
| **PDP** | Policy Decision Point. Função pura `decide()` que devolve uma `AdmissionDecision`. Sem I/O, processo, rede, LLM. | `tools/pdp.py` · ADR 0007 |
| **AdmissionDecision** | Saída do PDP: `outcome` (`deny`, `admit_read`, `approval_required`), `stable_reason_code`, `applied_rule_ids`, `intent_digest`, `effective_scope`, `bindings`, `decision_id`. Não é bearer token. | `tools/v1/schemas/admission-decision.schema.json` |
| **bindings** | Campos que a decisão vincula e o PEP revalida: `profile_sha256`, `policy_sha256`, `run_id`, `operation_id`, `effective_scope`, `max_output_bytes`. | `tools/pdp.py`, `runtime/pep.py` |
| **intent_digest** | SHA-256 do `ToolCallIntent` canônico. O PEP recomputa e compara. | idem |
| **PEP** | Policy Enforcement Point. `PolicyEnforcementPoint.enforce_read()` revalida bindings e descriptor imediatamente antes do efeito e consome a decisão uma vez. | `runtime/pep.py` · ADR 0008 |
| **Runtime** (local) | `LocalReadRuntime.read()`: abertura por handle com `O_NOFOLLOW`, `fstat` do fd, limite de bytes, política de paths sensíveis. Só leitura de arquivo regular. | `runtime/local_read_runtime.py` |
| **sensitive_path_policy_v1** | Política versionada de componentes de path negados (`.env`, `.env.*`, `.git`, `secrets`, `credentials`, `id_rsa`, `*.pem`, `*.key`). Só metadata; não inspeciona conteúdo. | `runtime/v1/policies/sensitive-path-policy-v1.json` |
| **WorkspaceManager** | Componente confiável do host. Único chamador de Git. Cria worktree detached de uma revisão configurada, emite descriptor, limpa só o que criou. | `runtime/workspace_manager.py` |
| **RuntimeWorkspaceDescriptor** | `workspace_id`, `canonical_root`, `task_ref`, `snapshot_digest`, `ownership=harness_owned`, `lifecycle` (`ephemeral_prepared`, `pending_cleanup`, `cleaned`). Só `ephemeral_prepared` lê. | `runtime/v1/schemas/runtime-workspace-descriptor.schema.json` |
| **snapshot_digest** | SHA-256 de `git ls-tree -r` canônico (`git-tree-items-v1`). No v1, `ToolCallIntent.task_ref` deve ser igual a ele. | `runtime/workspace_manager.py` |
| **ReadResult** | Saída do runtime: `outcome` (`delivered`, `deny`), `reason_code`, `bytes_read`, `taint`, `provenance`; `content` e `content_sha256` só em `delivered`. | `runtime/v1/schemas/read-result.schema.json` |
| **taint** | `{classification: untrusted_workspace_file, cannot_authorize: true}`. Todo conteúdo lido é não confiável e não pode alterar policy, scope ou instruções. | idem · ADR 0008 |
| **RuntimeAuditReceipt** | Recibo redigido: IDs, hashes, scope, `bytes_read`, `reason_code`, timestamp, `content_sha256` opcional. Nunca conteúdo ou path físico. `verify_receipt()` checa integridade. | `runtime/v1/schemas/runtime-audit-receipt.schema.json` |
| **EvidenceBundle** | Envelope JSON fechado que correlaciona decisão, bindings, workspace, projeção do `ReadResult` e receipt. Verificável offline. Não é autorização. | `integration/v1/schemas/evidence-bundle.schema.json` · ADR 0009 |
| **verify_offline** | Verificação pura e fail-closed do bundle: schema, canonicalização, digests, receipt, bindings. Sem rede, I/O ou reexecução. | `integration/local_evidence_bundle.py` |
| **logical_replay** | Projeção determinística da cadeia `intent → pdp → pep → evidence` a partir do bundle. Não reavalia nem executa. | idem |
| **json-c14n-v1** | Canonicalização usada em todos os digests: JSON UTF-8, chaves ordenadas, separadores compactos. | idem |
| **EvidenceTrialObservation / Report** | Observação por trial (bundle + outcome do runtime + latência) e relatório agregado com invariantes e `report_sha256`. | `integration/evidence_trial_metrics.py` |
| **reason code** | String estável que explica um `deny` ou resultado. Nunca contém conteúdo. Lista em [ARCHITECTURE.md §6](ARCHITECTURE.pt-BR.md#6-reason-codes-estáveis). | todos os módulos |
| **fail-closed** | Qualquer dado ausente, extra, inválido ou não revalidável produz `deny`. Não há fallback allow. | ADR 0007 |
| **skipped** | Controle que a plataforma não permite demonstrar. Reportado como tal, nunca como pass. | `hooks/test-*.py` |
| **Mode / RunConfig** | Cinco modos documentais (Prototyper, Builder, Sweeper, Grower, Maintainer) e configuração de run resolvida de forma pura. Modos selecionam políticas, não agentes. | `modes/` · ADR 0006 |
| **H1…H7** | Fatias do plano do Agent Development Harness (Spec aprovada). H1 contratos, H2 decisão, H3 enforcement, H4 evidência/trials, H5 contexto, H6 aprovação/review por risco, H7 learning controlado. | `docs/specs/agent-development-harness.md` |
