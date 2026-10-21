# Glossary

**English** · [Português (Brasil)](GLOSSARY.pt-BR.md)

Terms use the exact name used in the code and the ADRs. Paths are relative to `ai-development-framework/`.

| Term | Meaning | Where |
| --- | --- | --- |
| **ADF** | Agent Development Framework: a local-first control plane for coding agents + an adoption harness in the same monorepo. | root |
| **Harness** | Adoption and context layer: skills, commands, hooks, gates, evals, Graphify, RTK. Prepares intents and workspaces; does not enforce. | `skills/`, `commands/`, `hooks/` |
| **Adapter** | Local component that composes an `AdapterRequest` (intent, profiles, policy, context, descriptor) from a coding agent call. Declarative; does not decide or execute. | `integration/v1/schemas/adapter-request.schema.json` |
| **Registry** | Local, closed, versioned catalog of `ToolProfile`. Matching is exact on `tool_id` + `profile_sha256`. | `tools/v1` |
| **ToolProfile** | ADF-controlled interpretation of a tool: operations, `effect_classes`, `resource_kind`, `supported_scopes`, `max_risk`, `profile_sha256`. It is not a permission. | `tools/v1/schemas/tool-profile.schema.json` |
| **effect class** | `read`, `write`, `network`, `secrets`, `destructive`. In v1 only `read` can be admitted. | ADR 0007 |
| **ToolCallIntent** | Call intent, not execution: `tool_ref`, `operation_id`, `arguments`, `resource_scope`, `run_id`, `task_ref`, `requested_budget`, `policy_context_ref`. | `tools/v1/schemas/tool-call-intent.schema.json` |
| **PolicyBundle** | Versioned, hashed rules (`policy_sha256`) with declarative allowlists. Only restricts. | `tools/v1/schemas/policy-bundle.schema.json` |
| **PolicyContext** | References to the policy, `ResolvedRunConfig`, org/repo/mode restrictions, and the declared `runtime_capability`. A missing capability is "not demonstrated", never granted. | `tools/v1/schemas/policy-context.schema.json` |
| **PDP** | Policy Decision Point. Pure function `decide()` that returns an `AdmissionDecision`. No I/O, process, network, or LLM. | `tools/pdp.py` · ADR 0007 |
| **AdmissionDecision** | PDP output: `outcome` (`deny`, `admit_read`, `approval_required`), `stable_reason_code`, `applied_rule_ids`, `intent_digest`, `effective_scope`, `bindings`, `decision_id`. It is not a bearer token. | `tools/v1/schemas/admission-decision.schema.json` |
| **bindings** | Fields that the decision binds and the PEP revalidates: `profile_sha256`, `policy_sha256`, `run_id`, `operation_id`, `effective_scope`, `max_output_bytes`. | `tools/pdp.py`, `runtime/pep.py` |
| **intent_digest** | SHA-256 of the canonical `ToolCallIntent`. The PEP recomputes and compares it. | same |
| **PEP** | Policy Enforcement Point. `PolicyEnforcementPoint.enforce_read()` revalidates bindings and descriptor immediately before the effect and consumes the decision once. | `runtime/pep.py` · ADR 0008 |
| **Runtime** (local) | `LocalReadRuntime.read()`: handle-based open with `O_NOFOLLOW`, `fstat` on the fd, byte limit, sensitive-path policy. Regular file reads only. | `runtime/local_read_runtime.py` |
| **sensitive_path_policy_v1** | Versioned policy of denied path components (`.env`, `.env.*`, `.git`, `secrets`, `credentials`, `id_rsa`, `*.pem`, `*.key`). Metadata only; does not inspect content. | `runtime/v1/policies/sensitive-path-policy-v1.json` |
| **WorkspaceManager** | Trusted host component. The only caller of Git. Creates a detached worktree from a configured revision, emits a descriptor, cleans up only what it created. | `runtime/workspace_manager.py` |
| **RuntimeWorkspaceDescriptor** | `workspace_id`, `canonical_root`, `task_ref`, `snapshot_digest`, `ownership=harness_owned`, `lifecycle` (`ephemeral_prepared`, `pending_cleanup`, `cleaned`). Only `ephemeral_prepared` reads. | `runtime/v1/schemas/runtime-workspace-descriptor.schema.json` |
| **snapshot_digest** | SHA-256 of canonical `git ls-tree -r` (`git-tree-items-v1`). In v1, `ToolCallIntent.task_ref` must be equal to it. | `runtime/workspace_manager.py` |
| **ReadResult** | Runtime output: `outcome` (`delivered`, `deny`), `reason_code`, `bytes_read`, `taint`, `provenance`; `content` and `content_sha256` only on `delivered`. | `runtime/v1/schemas/read-result.schema.json` |
| **taint** | `{classification: untrusted_workspace_file, cannot_authorize: true}`. All content read is untrusted and cannot change policy, scope, or instructions. | same · ADR 0008 |
| **RuntimeAuditReceipt** | Redacted receipt: IDs, hashes, scope, `bytes_read`, `reason_code`, timestamp, optional `content_sha256`. Never content or a physical path. `verify_receipt()` checks integrity. | `runtime/v1/schemas/runtime-audit-receipt.schema.json` |
| **EvidenceBundle** | Closed JSON envelope that correlates decision, bindings, workspace, the `ReadResult` projection, and the receipt. Verifiable offline. It is not authorization. | `integration/v1/schemas/evidence-bundle.schema.json` · ADR 0009 |
| **verify_offline** | Pure, fail-closed verification of the bundle: schema, canonicalization, digests, receipt, bindings. No network, I/O, or re-execution. | `integration/local_evidence_bundle.py` |
| **logical_replay** | Deterministic projection of the `intent → pdp → pep → evidence` chain from the bundle. Does not re-evaluate or execute. | same |
| **json-c14n-v1** | Canonicalization used in all digests: UTF-8 JSON, sorted keys, compact separators. | same |
| **EvidenceTrialObservation / Report** | Per-trial observation (bundle + runtime outcome + latency) and an aggregated report with invariants and `report_sha256`. | `integration/evidence_trial_metrics.py` |
| **reason code** | Stable string that explains a `deny` or a result. Never contains content. List in [ARCHITECTURE.md §6](ARCHITECTURE.md#6-stable-reason-codes). | all modules |
| **fail-closed** | Any missing, extra, invalid, or non-revalidatable data produces `deny`. There is no fallback allow. | ADR 0007 |
| **skipped** | A control that the platform does not allow to be demonstrated. Reported as such, never as a pass. | `hooks/test-*.py` |
| **Mode / RunConfig** | Five documentation modes (Prototyper, Builder, Sweeper, Grower, Maintainer) and a run configuration resolved purely. Modes select policies, not agents. | `modes/` · ADR 0006 |
| **H1…H7** | Slices of the Agent Development Harness plan (approved Spec). H1 contracts, H2 decision, H3 enforcement, H4 evidence/trials, H5 context, H6 risk-based approval/review, H7 controlled learning. | `docs/specs/agent-development-harness.md` |
