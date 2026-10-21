# Local-first, evidence-first control plane

**English** · [Português (Brasil)](CONTROL_PLANE.pt-BR.md)

Date: 2026-09-25 · Repository version: 0.1.0 (experimental)

This document describes the product vision for the ADF control plane and what of it already exists on
`main`. Every claim points to code or an ADR. Anything without a pointer is future work.

## Thesis

Coding agents are already adopted. The problem is not building another agent. It is governing the tool
calls they make with a boundary that is **reproducible, verifiable, and portable**:

| Question | ADF answer | Where |
| --- | --- | --- |
| *Could* this call be admitted under the declared policy? | Pure, deterministic, fail-closed PDP | `tools/pdp.py` · ADR 0007 |
| Does the decision still hold at the moment of the effect? | The PEP revalidates every binding and consumes the decision once | `runtime/pep.py` · ADR 0008 |
| Did the effect stay within what was admitted? | Handle-confined read runtime, with a sensitive-path policy and a byte limit | `runtime/local_read_runtime.py` · ADR 0008 |
| Can it be proven later, without re-executing anything? | Closed `EvidenceBundle`, `verify_offline` and `logical_replay` with no I/O | `integration/local_evidence_bundle.py` · ADR 0009 |
| What should be measured to know whether this has value? | Redacted aggregates: admit/deny, binding mismatch, sensitive path, valid bundles, latency | `integration/evidence_trial_metrics.py` · ADR 0009 |

## Normative principles

Extracted from ADRs 0007–0009. These are implementation rules, not aspirations.

1. **`PDP ≠ PEP ≠ Runtime ≠ sandbox`.** Each layer keeps or narrows scope, effects, and budget; it never widens them.
2. **Description is not permission.** `ToolCapability`, `ToolProfile`, manifest, MCP annotation, `extensions`, prompt, and model response authorize nothing. An MCP annotation enters at most as evidence.
3. **Default deny.** Data that is missing, extra, non-canonical, unversioned, hash-divergent, or without an **exact** match in the Registry produces `deny` with a stable reason code.
4. **A decision is not a bearer token.** `admit_read` binds `run_id`, `profile_sha256`, `policy_sha256`, `operation_id`, `effective_scope`, `max_output_bytes`, and `intent_digest`. The PEP recomputes the digest and compares everything before opening the file. No TTL in v1: validity is revalidation.
5. **Read content is tainted.** Every `ReadResult` carries `taint: {classification: untrusted_workspace_file, cannot_authorize: true}`. The Harness passes it to the model only when `outcome=delivered`, and the content never changes policy, scope, or instructions.
6. **No LLM on the critical path.** No classifier, Decision Model, or external service decides authorization. A future heuristic may only add `deny` or `approval_required`; it may never make something permissive without its own ADR.
7. **Evidence without content.** Receipts and bundles store IDs, hashes, sizes, reason codes, and provenance. Never content, physical path, root, raw arguments, or secrets.
8. **Skipped is never green.** A control that the platform does not allow to be demonstrated reports `skipped` or fails.

## The three delivered primitives

### H2-02 · Registry + PDP

`decide(intent, profiles, policy, context, schemas)` returns exactly one canonical
`AdmissionDecision`. Order: it validates envelopes and hashes, finds exactly one `ToolProfile` by `tool_id` +
`profile_sha256` and exactly one operation, rejects arguments with sensitive names, validates arguments
against the local schema, normalizes scope, intersects the context/policy/mode/profile allowlists, and computes
the smallest `max_output_bytes`. Only `effect_classes == {read}` can become `admit_read`.

There is no fallback allow, wildcard, similarity-based selection, or textual shell. The module does not import
subprocess, socket, HTTP, MCP, or Git.

### H3-01 · PEP + local read runtime

`PolicyEnforcementPoint.enforce_read(...)` accepts only `outcome=admit_read`, revalidates contracts and
bindings, requires a `harness_owned` `RuntimeWorkspaceDescriptor` in `ephemeral_prepared`, and calls
`LocalReadRuntime.read(descriptor, path, budget)`. The runtime opens each path component with
`dir_fd` + `O_NOFOLLOW`, uses the handle's `fstat` to validate that the target is a regular file and fits within the limit, and
denies sensitive paths through `sensitive_path_policy_v1` (`.env`, `.env.*`, `.git`, `secrets`,
`credentials`, `id_rsa`, `*.pem`, `*.key`). After any attempt the descriptor moves to
`pending_cleanup`; cleanup removes only a worktree that the `WorkspaceManager` itself created.

The `WorkspaceManager` is the **only** Git caller. It runs before the PEP with a repository and revision
configured by the host, and produces a deterministic `snapshot_digest` (`git-tree-items-v1`) that
`ToolCallIntent.task_ref` must equal. The agent supplies no root, revision, or cwd.

### H4-01 · Evidence Bundle

`compose(request, schemas, pep)` runs H2-02 and, if admitted, H3-01, and returns an `EvidenceBundle`
with `bundle_id` and `bundle_sha256` (SHA-256 over canonical JSON `json-c14n-v1`). `verify_offline`
checks schema, canonicalization, digests, receipt integrity, binding coherence, and
`read_result_digest`. `logical_replay` projects the `intent → pdp → pep → evidence` chain from
the bundle. `is_authorization(bundle)` always returns `False`.

`aggregate_trial_observations` (H4-01b) sums only observations whose bundle verifies offline and whose
reason code is in the versioned mapping; invalid ones count in `evidence_bundle_invalid_total`.
`make local-evidence-pilot` (H4-01c) runs three trials over internal revisions and prints only the
verified aggregate report.

## Honest metrics

What ADF can measure today, in controlled runs, in aggregated and redacted form:

```text
decisions_total · admit_read_total · deny_total
binding_mismatch_total · sensitive_path_denied_total · invalid_contract_total
evidence_bundle_valid_total · evidence_bundle_invalid_total
human_intervention_required_total · decision_latency_ms {count,sum,min,max}
```

What is **not** claimed: incidents prevented in production, financial savings, ROI, SOC 2 or
EU AI Act compliance, safe autonomy, coverage of real attacks. These claims require trials
with design partners and data that do not exist yet.

## What is not in the product (at this stage)

| Item | State | Condition to enter |
| --- | --- | --- |
| `write`, `network`, `secrets`, `destructive` | `deny` by construction | Own ADR + PEP/Runtime with idempotency key, preflight, and bound approval |
| Host/process sandbox, Docker, gVisor | does not exist | H3-02, blocked until there is usage evidence |
| Shell, subprocess, real MCP, secrets manager | forbidden in the PDP/PEP/Runtime | Own ADR |
| SaaS, SSO/RBAC, dashboard, central database, billing | do not exist | future commercial decision (H4+) |
| Public CLI / SDK / npm / PyPI | not published | own decision; at most a validation CLI with no effects |
| Local Python package (`pyproject.toml`, `make install-dev`) | editable install of the clone, no registry | only replaces `sys.path` with imports; does not change admission, enforcement, or evidence |
| Decision Model / Jev / Laya | not used; J0 only defines a typed residual port | own trials, deterministic grader, and calibration |
| Operational human approval (`approval_required`) | the enum exists, it is not emitted | H6 |
| Read-only adapter for Claude Code (`Read`) | exists as an opt-in PreToolUse gate; see [Read-only adapter](#read-only-adapter-p0) | a second adapter only when it shares the same interface |
| A2A edge (loopback HTTP, bearer + scopes) | A2A-1 to 6: confined read via the PEP with `CallerPrincipal`, evidence, validated delegation, resumable `auth-required`, and `input-required` behind a host flag; see [A2A edge](#a2a-edge-a2a-1-to-6) | Token Exchange endpoint (ADR 0019, deferred), shared task store, DPoP/mTLS (A2A-8b), signed card (A2A-9), and `write` require their own ADR; TLS only via proxy (A2A-8a) |

## Typed residual signal (J0)

`tools/decision_signal.py` defines `TypedQuestion` (`yes_no`, `choice`, or `score`),
`DecisionSignal`, the `DecisionSignalProvider` port, and the local `NoopDecisionSignalProvider` provider.
The v1 JSON contracts are closed: there is no free-form prompt and no authorization field. The noop always
abstains and performs no I/O. `request_residual` requires `enabled=True` and an `admit_read` already emitted
by the hard rules; `deny` does not call the provider. A failure, an invalid response, or a missing provider
results in abstention. The returned signal neither changes nor creates an `AdmissionDecision`.

J0 only offers the port; the PDP, adapter, PEP, and runtime do not call it. The current flow therefore remains
deterministic and off by default. The idea is similar to System-One/JEV, without consuming the
commercial Jev product, Laya, an LLM, or an external service. A real provider and any use of the signal
in policy require a later decision and evaluation; a typed signal is not authorization.

## Adapter attempt journal (P0-A, proposal on a branch)

The additive contract `integration/v1/schemas/adapter-attempt-event.schema.json` records
`started` and `completed` in `<evidence_dir>/_attempts/<attempt_id>.jsonl` for every call
that reaches `LocalReadAdapter.read`. The start is persisted before validation/preparation;
the end only after cleanup. A pre-admission deny still has no bundle when there is no
valid request, but it has a redacted journal when evidence is available.

`verify_attempt(events, schema)` verifies structure, hashes, and correlation offline; a start
alone is `incomplete`, never success. `complete` includes denials and verifies only
structure/integrity. The payload records the result computed after cleanup and before return,
with no confirmation of receipt by the harness. A cleanup failure is recorded in the end event even if the bundle
receipt recorded a delivered read; the bundle is neither rewritten nor reauthorized.
A failure to create/finalize the journal prevents delivery with `attempt_evidence_failed`.
If the final fsync and the ftruncate rollback both fail, a complete journal may contain the
computed result `delivered` despite a deny return; durability is not confirmed.

The v1 trial counters still ingest only `*.json` bundles: they do not include
journals and do not start demonstrating final success. Rejections that happen earlier in the hooks, and tools
that are not covered, remain outside the capture. Details, contract, and limits in
[ADR 0010 (Accepted)](architecture-decision-records/0010-adapter-attempt-lifecycle.md).

## Read-only adapter (P0)

`integration/local_read_adapter.py` composes, for **one** read intent, the chain already delivered:
`build_request` → `compose` (H2-02 → H3-01) → `verify_offline` → redacted bundle persisted to
`docs/observability/evidence/<run_id>/<bundle_id>.json` (dir `0700`, file `0600`, gitignored).
The host fixes the repository, revision, budget, and evidence directory; the agent supplies only a relative
path. Content leaves the adapter only with `outcome=delivered`, always with `taint`
`untrusted_workspace_file`, and never enters the bundle. A failed cleanup withdraws the content and returns
`deny(workspace_worktree_cleanup_failed)`. The PDP and PEP do not change.

`hooks/claude-code-read-gate.py` is the first wired agent path: a Claude Code
`PreToolUse` hook for the `Read` tool. It makes `file_path` relative lexically against the
trusted repository (`..` survives and is denied by the contract), uses `session_id` as `run_id`,
calls the adapter, and answers `allow`/`deny` with `reason_code` and `bundle_id`. Any other tool, an
extra field in `tool_input`, a path outside the root, or an exception produces `deny`.

To use it in another repository, the host/wrapper configures the environment **before** starting the
agent or the hook. Install the package locally with `make install-dev` and point the hook command
to the absolute path of `claude-code-read-gate.py` in this clone:

```bash
export ADF_TRUSTED_REPOSITORY="${CLAUDE_PROJECT_DIR:?}"  # or the project's absolute path
export ADF_TRUSTED_REVISION=HEAD                     # optional; HEAD is the default
export ADF_EVIDENCE_DIR="$ADF_TRUSTED_REPOSITORY/.adf/evidence"
export ADF_MAX_OUTPUT_BYTES=1048576                  # optional; 1 MiB is the default
```

`ADF_TRUSTED_REPOSITORY` must be an existing absolute directory. Outside the ADF layout,
`ADF_EVIDENCE_DIR` must also be absolute and explicit; the evidence root created by the adapter,
the session directories, and the files have permissions `0700`, `0700`, and `0600`. In the ADF layout,
without these variables, the defaults are the monorepo root, `HEAD`, 1 MiB, and
`docs/observability/evidence`. If `CLAUDE_PROJECT_DIR` points to another project and there is no
`ADF_TRUSTED_REPOSITORY`, or if the configuration is invalid, the gate denies with
`host_configuration_invalid`. Fields in the tool payload do not configure root, revision, evidence,
or budget. The environment selects host parameters; it is not authorization by itself: the PDP and PEP
still validate every read.

<a id="policy-do-host-p0-b-opt-in-na-branch"></a>
### Host policy (P0-B, opt-in on the branch)

Without a policy configuration, the adapter keeps the **reference demo**, which synthesizes
grants for the requested path. To apply a previously configured allowlist, the host
supplies a closed JSON with `schema_version: "1.0"`, `profiles` (one profile/one operation),
`policy`, and `context`, in the existing v1 contracts. Use the artifacts
in `tools/v1/examples/{tool-profile,policy-bundle,policy-context}/valid/read-worktree.json` as a reference.
The host reviews exact scopes, budgets, and bindings, and pins the context's run ID to the harness
session ID before the intents. There is no wildcard or DSL.

```bash
export ADF_READ_POLICY_FILE=/absolute/path/approved-policy.json
export ADF_READ_POLICY_SHA256="$(python3 -c 'import hashlib,json,os; v=json.load(open(os.environ["ADF_READ_POLICY_FILE"])); print(hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest())')"
```

Computing the pin is part of the host's trusted configuration; do it once after
review, and keep the file and the pin fixed for the session. Recomputing it on every request would eliminate
detection of a file swap. Do not change internal hashes to accommodate an intent.
The pin uses `json-c14n-v1`, not a hash of the file's bytes/formatting.

The adapter validates the pin, versions, shape, schemas, and internal hashes before preparing the
workspace; a partial or invalid configuration denies with `host_policy_invalid`, with no
fallback to the demo. Each intent uses a copy of the loaded artifacts, without widening scope,
rewriting the run ID, or modifying the ceiling. The PDP/PEP deny a request above the ceiling. An adapter
keeps its configuration; a new process with an old pin denies a changed file.
Payload fields do not configure policy. The host remains the trust
boundary; these pins do not contain an agent that has permission to change its environment.
See [ADR 0011 (Accepted)](architecture-decision-records/0011-pinned-host-read-policy.md).

Enable it (opt-in, in the project's `.claude/settings.json` or `settings.local.json`;
replace `ABS_ROOT` with the output of `pwd -P`):

```json
{"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": "ABS_ROOT/.venv/bin/python3 ABS_ROOT/ai-development-framework/hooks/claude-code-read-gate.py"}]}]}}
```

Documented path without Claude Code (the same code the hook runs):

```bash
printf '{"hook_event_name":"PreToolUse","tool_name":"Read","session_id":"manual-1","tool_input":{"file_path":"%s/README.md"}}' "$PWD" \
  | python3 ai-development-framework/hooks/claude-code-read-gate.py
ls ai-development-framework/docs/observability/evidence/manual-1/
```

What is **not** covered, deliberately:

- The hook decides `allow`/`deny`; delivery of the content to the model is still done by the native `Read`
  tool, outside the confined runtime. The bundle proves the decision and a confined read of the `HEAD`
  snapshot, not the bytes the agent received (the checkout may have uncommitted changes).
- Nothing prevents the agent from reading via `Bash`, another tool, or another process. There is no bypass-proof claim.
- A future typed residual signal does not authorize a read; deterministic rules and the PEP remain
  mandatory.
- One Git worktree per read (`WorkspaceManager`); real latency cost, measured by
  `decision_latency_ms`, with no cache.
- Contract denies (`invalid_referenced_contract`, a path with `..`) do not generate a bundle: the request never
  validated. PDP denies that occur before scope resolution (`invalid_scope`, `invalid_arguments`,
  `run_binding_mismatch`…) generate a bundle with `effective_scope: null`, which verifies offline since
  2026-10-19 (WP1b); before that they counted in `evidence_bundle_invalid_total`. An admit with a `null` scope
  remains invalid: the receipt requires the scope.
- The Claude Code gate covers only `Read`; the Codex P4 gate below covers only allowlisted Bash.
- Since ADR 0023 (Accepted), the local edges derive a `CallerPrincipal` from the harness (`claude:<agent_type>`);
  it appears in the journal and in the span, not in the bundle, and does not change the decision yet.

## Codex Bash read-equivalent (P4)

In Codex CLI 0.157.0, `PreToolUse` receives `tool_name: "Bash"` and
`tool_input.command`; a deny uses `hookSpecificOutput.permissionDecision: "deny"`.
After `delivered`, the hook returns `{}` (no-block); in this version,
`permissionDecision: "allow"` without `updatedInput` marks the hook as failed.
`hooks/codex-bash-read-gate.py` admits only `cat PATH` or `cat -- PATH`, with a
single literal ASCII path and no expansion, options, pipe, redirection, or other command.
An ambiguous `cat`, including after shell separators, is denied; non-`cat` commands return `{}` and follow Codex's normal
approval policy. `head`, `sed`, `awk`, `python -c`, and other means of reading
are not part of this grammar.
**Codex gate covers allowlisted read-equivalent Bash, not all file access.**

The host sets `ADF_TRUSTED_REPOSITORY` (an existing absolute directory),
`ADF_EVIDENCE_DIR` (an absolute directory), and optionally `ADF_TRUSTED_REVISION`
(`HEAD`) and `ADF_MAX_OUTPUT_BYTES` (1048576). Configure them in the process that starts
Codex, without accepting values from the agent. An absolute path is made relative against the root;
a relative path uses the Codex session's cwd. The gate shares settings validation and the P0 adapter
with Claude. The `allow` decision means that the adapter successfully read
a confined snapshot and persisted evidence, after which native Bash still runs
and delivers its own bytes. The snapshot may differ from the active checkout.
If `tool_input.workdir` is present, the relative path uses that absolute directory;
unknown fields in a read are denied. Without the two mandatory root and evidence
variables, the Codex gate denies reads with `host_configuration_invalid`.

This repository enables the gate in [`.codex/hooks.json`](../../.codex/hooks.json):

```json
{"hooks":{"PreToolUse":[{"matcher":"^Bash$","hooks":[{"type":"command","command":"/bin/bash \"$(git rev-parse --show-toplevel)/ai-development-framework/hooks/codex-bash-read-gate.wrapper.sh\"","timeout":30,"statusMessage":"Checking ADF read policy"}]}]}}
```

The Git root resolves the absolute command even when Codex starts in a subdirectory.
The wrapper `hooks/codex-bash-read-gate.wrapper.sh` resolves the root from the script itself,
exports the defaults `ADF_TRUSTED_REPOSITORY=<root>`, `ADF_TRUSTED_REVISION=HEAD`, and
`ADF_EVIDENCE_DIR=<root>/ai-development-framework/docs/observability/evidence`, and runs
`exec` of `<root>/.venv/bin/python3` with the absolute path of the gate. Host overrides
remain valid; `ADF_MAX_OUTPUT_BYTES` keeps the P3 default of 1 MiB.
Create `.venv` at the root and run `make install-dev` with it active before starting Codex.
There are no machine-specific paths in the config or the wrapper; the same clone works on macOS/Linux.

The `.codex/` project must be trusted. Open `/hooks` in Codex CLI to review
and trust the exact definition; changes require a new review. Hooks must be
active (`[features] hooks = true`, the current default). [OpenAI Docs: Hooks](https://learn.chatgpt.com/docs/hooks)
documents the configuration, the input/output format, and the limitations.

| Surface | ADF coverage | Residual risk |
| --- | --- | --- |
| Claude Code `Read` | PDP → PEP → confined read + bundle before the native `Read` | Native `Read` may deliver bytes that differ from the snapshot |
| Codex `Bash` allowlisted `cat` | The same chain before native Bash | Bash may deliver different bytes; the parser covers only the literal command |
| Other paths (other Bash, tools, processes) | No ADF P4 decision | They may read files without going through the adapter; hooks are a guardrail, not a sandbox |

Manual test of the hook contract:

```bash
export ADF_TRUSTED_REPOSITORY="$(pwd -P)"
export ADF_EVIDENCE_DIR="$ADF_TRUSTED_REPOSITORY/ai-development-framework/docs/observability/evidence"
export ADF_TRUSTED_REVISION=HEAD
printf '{"hook_event_name":"PreToolUse","tool_name":"Bash","session_id":"manual-codex-allow","tool_input":{"command":"cat %s/README.md"}}' "$ADF_TRUSTED_REPOSITORY" \
  | .venv/bin/python3 ai-development-framework/hooks/codex-bash-read-gate.py
printf '{"hook_event_name":"PreToolUse","tool_name":"Bash","session_id":"manual-codex-deny","tool_input":{"command":"cat %s/.env"}}' "$ADF_TRUSTED_REPOSITORY" \
  | .venv/bin/python3 ai-development-framework/hooks/codex-bash-read-gate.py
printf '{"hook_event_name":"PreToolUse","tool_name":"Bash","session_id":"manual-codex-pass","tool_input":{"command":"ls -la"}}' \
  | .venv/bin/python3 ai-development-framework/hooks/codex-bash-read-gate.py
```

The first and the third return `{}`: to distinguish an admitted read from a
passthrough, check the new bundle in `ADF_EVIDENCE_DIR/manual-codex-allow/`. The second
returns `deny` with `adf: deny/<reason_code>`.

After a real session, aggregate the evidence without re-executing effects:

```bash
EVIDENCE_DIR=ai-development-framework/docs/observability/evidence make local-evidence-trial
```

On macOS, create/activate `.venv` with the same `python3` that the hook command will use,
run `make install-dev`, and check `python -c 'import tools, runtime, integration'`.
The committed wrapper already avoids depending on `PATH` or on interactive-shell exports
for Python and the host defaults. For another layout, adjust the configuration reviewed
by the operator; do not accept root, revision, evidence, or budget coming from the tool payload.

Do not put secrets in the wrapper. Prefer evidence under the repo or
`~/Library/Application Support/adf/evidence`, outside folders synced by iCloud.
Normal repo reads do not require disabling SIP or granting Full Disk Access. If
macOS denies evidence creation (`Operation not permitted`), the read fails closed
with `adapter_failed`; test in a normal directory without TCC prompts, without opening
global permissions. The Linux CI and local macOS tests must report any unavailable platform
as `skipped`, never as green.

## Mediated read experiment (P0-C, separate branch)

The opt-in local MCP server `read_snapshot` returns to the test client the
adapter's own text, checking SHA-256 and size against the receipt of the
same execution. In-memory and stdio tests include an edited checkout,
a denial, and missing configuration. This does not reclassify the `Read`/`cat` hooks:
they remain `gate_only`, with no guarantee of the identity of the native bytes.
See the [coverage matrix](integrations/coverage-2026-09-29.md) and
[ADR 0012 (Accepted)](architecture-decision-records/0012-mediated-stdio-read.md).

<a id="borda-a2a-a2a-1-a-6"></a>
## A2A edge (A2A-1 to 6)

[ADR 0013](architecture-decision-records/0013-a2a-edge-authn-authz.md) (Accepted) and
[ADR 0014](architecture-decision-records/0014-caller-principal-envelope.md) (Accepted),
[ADR 0015](architecture-decision-records/0015-a2a-delegation-chain.md),
[ADR 0016](architecture-decision-records/0016-a2a-auth-required-task.md), and
[ADR 0017](architecture-decision-records/0017-a2a-rs256-pinned-jwks.md) (Accepted);
[ADR 0018](architecture-decision-records/0018-a2a-input-required-confirmation.md) and
[ADR 0019](architecture-decision-records/0019-a2a-token-exchange-seam.md) (Accepted). A2A only
announces the required authentication; who may do what is still PDP → PEP → Evidence.
`integration/a2a_gateway.py` is a transport and identity edge, equivalent to the
Claude/Codex gates:

```text
Bearer (header) → AuthN → CallerPrincipal → skill/scope → LocalReadAdapter
  → ToolCallIntent v1 (unchanged, no claims) + principal → PDP → PEP (revalidates principal)
  → confined runtime → EvidenceBundle v1 + A2AEvidenceRecord (evidence/_a2a/)
```

| Layer | Implemented | Residual |
| --- | --- | --- |
| 1. AuthN | `Authorization: Bearer` JWT: RS256 over a local JWKS pinned by the host (`ADF_A2A_JWKS_FILE` + `ADF_A2A_JWKS_SHA256`; the gateway holds no signing key) or pilot HS256; signature, `alg`, `kid`, `iss`, exact `aud`, `exp`, `nbf`, `sub`; `exp` at most 1 h ahead (`token_lifetime_exceeded`) | no automatic JWKS fetch/rotation; no DPoP/mTLS (8b deferred): TLS only via a proxy in front (A2A-8a), a stolen token is valid until `exp` (≤ 1 h) |
| 2. AuthZ | `SKILL_SCOPES` → pinned host policy (ADR 0011) → PDP → PEP; an unknown skill/missing scope denies before the PDP | a scope does not admit on its own; without host policy → `host_policy_invalid` (never demo mode) |
| 3. Delegation | closed `act` `{sub, act?}`, no cycles, depth ≤ 8 (`delegation_chain_invalid`); a delegated token is limited to `DELEGABLE_SCOPES` (`scope_escalation_denied`); exact `aud` blocks passthrough; `exchange_hs256` is an RFC 8693 test double (scopes ⊆ parent, `exp` ≤ parent) | exchange endpoint and RS256 issuance deferred (ADR 0019, won't do yet: the gateway does not become an issuer); the ceiling on receipt is policy, not cryptographic proof; the issuer must be trusted |
| 4. `auth-required` | `principal_expired` in the PEP → Task `auth-required`, with no effect; resuming with `message.taskId` + a new token = a complete new admission; same `sub`/skill/path, TTL 300 s, single use; 409 `task_*` | in-memory store, single process: restart → `task_not_found` |
| 5. `input-required` | a skill marked by the host (`ADF_A2A_CONFIRM_SKILLS`) pauses before PDP/PEP (`input_required`, no effect); resuming with `taskId` using a token from the same `sub`, without `act`, with `human:confirm` (not delegable) = a new admission, record `confirmation: human_confirmed`; otherwise 403 `human_confirmation_required` | the edge proves the scope, not the human (that is the IdP's job); no irreversible skill exists; in-memory store |

Fail-closed in this order: a body with a sensitive key or a value shaped like a JWT/Bearer →
`credential_in_payload`; a request outside the closed schema (including `decision_id`, a bundle, or a grant in the body)
→ `invalid_request`; AuthN → 401 + `WWW-Authenticate`; skill/scope → 403; then the
existing `LocalReadAdapter` (the host's ephemeral workspace, PDP, PEP, runtime, bundle, cleanup).

**Identity without touching the intent (ADR 0014).** Claims never enter the v1 `ToolCallIntent`. The
gateway creates a closed `CallerPrincipal` (`sub`, `scopes`, `act`, `token_aud`, `authn_method`,
`expires_at`). The PDP validates the principal (`invalid_principal`), but the v1 decision is identical with or
without it. The PEP revalidates the principal at the effect (`invalid_principal`, `principal_expired`) before the
existing bindings. Local edges pass `principal=None`, so nothing changes for Claude, Codex, or MCP.
The two new codes were added to the attempt journal enum and to the metrics mapping;
old evidence remains valid.

**Delegation (ADR 0015).** The gateway does not accept a downstream token in the body (closed schema,
`credential_in_payload`) and makes no outbound calls. Each hop's token must be issued for
this gateway's `aud`; the user's token for another agent falls into 401. The valid `act` chain goes
to the principal and to the record (only the `sub` values). A delegated token with a scope above the host ceiling
is denied in full, with a record, instead of having the excess ignored. Scope reduction during derivation
exists only in the `exchange_hs256` test double (with no public endpoint); in production it belongs to a trusted AS.

**Tasks (ADR 0016).** A task only correlates; it carries no authority. A `taskId` that is unknown,
expired, already consumed, from another `sub`, or with another skill/path is denied with 409 and a record, without
reaching the adapter. The result of the resumption carries `task.status.state` `completed` or `failed`.

**Response and evidence.** `delivered` carries `content` (untrusted text, `cannot_authorize`),
`effect: "read"`, `taint`, and `audit` (`sub`, `act`, `skill`, `outcome`, `reason_code`,
`decision_id`, `bundle_id`, `record_id`). Every request that got past AuthN writes an
`A2AEvidenceRecord` to `evidence/_a2a/<record_id>.json` (`0700`/`0600`, no overwrite), linked
to the bundle. `verify_record` checks schema, hash, principal, the link to the bundle, and `verify_offline`.
If evidence fails or does not verify → `500 a2a_evidence_failed` and no byte leaves. The consumed
decision does not authorize a second effect. A 401 has no identity, so it only produces the log line.

Honest residual: AuthN only at the transport; skill/card ≠ authorization; the edge is not a host sandbox,
and an agent with another read route bypasses it; HTTP only on `127.0.0.1`, with no TLS of its own (TLS via proxy, A2A-8a); the log
records only method, route, and status; the record proves what the edge saw, not the origin of the token; the
`act` chain is asserted by the issuer, not verified hop by hop; with the HS256 pilot, whoever holds the
secret can issue any chain (with RS256 that requires the IdP's private key); RSA verification is our own
stdlib code, tested (mutation + `openssl` oracle), not an audited library; a stolen token, including a derived one, is valid until `exp`. Pilot
(without `ADF_TRUSTED_REPOSITORY`, the host is the clone itself and evidence goes to
`docs/observability/evidence`):

```bash
export ADF_A2A_HS256_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export ADF_READ_POLICY_FILE=/abs/host-policy.json ADF_READ_POLICY_SHA256=<pin>   # policy approves README.md
python3 -m integration.a2a_gateway serve &
TOKEN="$(python3 -m integration.a2a_gateway mint agent-alpha workspace:read)"   # pilot IdP stand-in; 1 h by default, --ttl up to 86400
curl -s http://127.0.0.1:8765/.well-known/agent-card.json
curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $TOKEN" -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m1","parts":[{"kind":"data","data":{"skill":"read_workspace_file","arguments":{"path":"README.md"}}}]}}}'
```

`input-required` pilot (ADR 0018): the host marks the skill; the agent pauses, the human confirms. The pause,
the confirmed resumption, and a resumption deny carry `effect_binding` = digest of `sub` + skill + `path`
(ADR 0022, Accepted): the auditor checks offline that the confirmed effect is the one that was paused.

```bash
ADF_A2A_CONFIRM_SKILLS=read_workspace_file python3 -m integration.a2a_gateway serve &
MSG='{"kind":"message","role":"user","messageId":"m1","parts":[{"kind":"data","data":{"skill":"read_workspace_file","arguments":{"path":"README.md"}}}]'
TASK="$(curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $TOKEN" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"message/send\",\"params\":{\"message\":$MSG}}}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["task"]["id"])')"
HUMAN="$(python3 -m integration.a2a_gateway mint agent-alpha 'workspace:read human:confirm')"
curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $HUMAN" -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"message/send\",\"params\":{\"message\":${MSG},\"taskId\":\"$TASK\"}}}"
```

RS256 pilot (ADR 0017): the IdP signs with the private key; the host pins only the public JWKS.

```bash
export ADF_A2A_JWKS_FILE=/abs/jwks.json ADF_A2A_JWKS_SHA256="$(sha256sum /abs/jwks.json | cut -d' ' -f1)"
unset ADF_A2A_HS256_SECRET   # with a JWKS configured, HS256 is never accepted
python3 -m integration.a2a_gateway serve &
curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $RS256_TOKEN_FROM_IDP" -d '…'
```

**Transport (A2A-8a).** The Python process listens only on `127.0.0.1` (`make_server` refuses
any other host with `loopback_only`; a test pins this). To expose the edge outside the machine,
a proxy **on the same host** terminates TLS and forwards to loopback; the public bind belongs to the proxy,
is a host decision, and does not change AuthN, PDP, PEP, or evidence. Caddy example (access logs
off by default; if turned on, `Authorization` is redacted):

```caddyfile
a2a.example.internal {
	tls /etc/adf/a2a.crt /etc/adf/a2a.key
	request_body {
		max_size 64KB
	}
	@a2a path / /.well-known/agent-card.json
	handle @a2a {
		reverse_proxy 127.0.0.1:8765
	}
	handle {
		respond 404
	}
}
```

nginx equivalent: `listen 443 ssl; ssl_protocols TLSv1.3; client_max_body_size 64k;` and
`location = /` + `location = /.well-known/agent-card.json` with `proxy_pass http://127.0.0.1:8765;`.
Never put `$http_authorization` in a `log_format`.

Transport residual: TLS protects the bearer in transit, but does not bind it to the sender — a stolen
token remains valid until `exp` (≤ 1 h). DPoP/mTLS (A2A-8b) require their own ADR and remain
deferred. The card still announces a loopback `url`; the remote client uses the proxy URL. The
proxy is a new exposed component: patching, certificates, and rate limiting belong to the host.

## Observability (OTel, ADR 0020)

[ADR 0020](architecture-decision-records/0020-control-plane-otel-export.md) (Accepted). Off
by default. With `ADF_OTEL_ENABLED=1`, each A2A request becomes an `adf.a2a.request` span sent over
OTLP/HTTP JSON (stdlib, no dependency) **after** the final decision: status, `outcome`,
`reason_code`, `skill`, `act_depth`, `task_state`, and the ids `decision_id` / `bundle_id` /
`record_id`. Never the token, `sub`, `path`, or content; a suspicious value discards the whole span.
A collector that is down or an exporter error → one line on stderr and the same response (fail open).

Residual: **trace ≠ evidence.** The span may be missing and is not signed; audit is the Evidence
Bundle + `verify_offline`, and trial metrics remain in `make local-evidence-trial`.

```bash
docker compose -f docs/observability/docker-compose.otel.yml up -d     # Jaeger, loopback only
export ADF_OTEL_ENABLED=1 ADF_OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
python3 -m integration.a2a_gateway serve &                              # + A2A pilot env above
BODY='{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m1","parts":[{"kind":"data","data":{"skill":"read_workspace_file","arguments":{"path":"README.md"}}}]}}}'
curl -s -X POST http://127.0.0.1:8765/ -d "$BODY"                                                  # 401 auth_missing
curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $(python3 -m integration.a2a_gateway mint agent-alpha other:read)" -d "$BODY"  # 403
curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $TOKEN" -d "$BODY"                # 200 read_delivered
# http://127.0.0.1:16686 → service adf-control-plane → three adf.a2a.request spans
```

With `ADF_A2A_CONFIRM_SKILLS=read_workspace_file`, the pause appears as `reason_code=input_required`,
`task_state=input-required`.

**Local edges ([ADR 0021](architecture-decision-records/0021-local-edge-otel-spans.md)).** With the same
`ADF_OTEL_ENABLED=1`, each decision of the Claude `Read` gate, the Codex `cat` gate, and the MCP tool becomes an
`adf.local_read.request` span with only `adf.edge` (`claude_read` | `codex_bash` | `mcp_read`), `outcome`,
`reason_code`, `bundle_id`, and `duration_ms`. Never `file_path`, `command`, `session_id`, the repo root, or
content. The hook waits for the send for at most `ADF_OTEL_FLUSH_MS` (default 300 ms, ceiling 2000), only with OTel
on, and does not write to stderr if the export fails. An A2A read still produces a single span
(`adf.a2a.request`): the `LocalReadAdapter` does not export. From span to bundle: `adf.bundle_id` →
`evidence/<run_id>/<bundle_id>.json` → `verify_offline`.

**Two screens (Langfuse + ADF).** The same exporter can send to Langfuse's OTLP endpoint
(`ADF_OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel` +
`ADF_OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64(pk:sk)>`; headers only over `https` or
loopback, never logged). Langfuse shows what the agent did; ADF decides and proves. Jaeger
keeps working. Correlation span → `evidence/_a2a/<record_id>.json` → `verify_record`:
[runbook](observability/LANGFUSE.md). A run with real HTTP, screenshots, and a benchmark:
[live A2A trials](observability/trials/a2a-live/README.md). Residual: the content of the agent's traces in Langfuse
depends on the privacy configured in the agent's integration; ADF spans remain redacted.

## For design partners

What the repository offers for evaluation today:

- run `make local-evidence-trial` (P2) and read the redacted aggregate; see [Local trial](#local-trial-p2);
- run `make local-evidence-pilot` and inspect the aggregate report;
- read the [live A2A trial](observability/trials/a2a-live/README.md) (T1–T7 matrix, verified evidence,
  Jaeger screenshots, benchmark) and repeat it on your own host;
- run the negative matrix (`hooks/test-tool-admission.sh`, `hooks/test-runtime-read.sh`,
  `hooks/test-local-evidence-bundle.sh`) and read the reason codes;
- read the schemas in `tools/v1`, `runtime/v1`, `integration/v1` and the normative oracles in
  `*/v1/tests/normative-oracles.json`.

What we ask in return: real (redacted) read intents, cases where the `deny` would be
wrong, and the list of sensitive files that the v1 policy does not cover yet.

### Local trial (P2)

To install in another repository and capture real sessions without mixing smoke runs and
earlier evidence, follow the [collection protocol](trials.md).

`hooks/run-local-evidence-trial.py` turns the P0 adapter and the H4-01b metrics into a repeatable,
local, redacted trial. One source per run, a single report format:

| Source | Command | What it measures |
| --- | --- | --- |
| Fixed suite (`suite_version` 1.0) | `make local-evidence-trial` | five real adapter reads over the checkout at `HEAD`: `README.md` (admit), `secrets/token` (sensitive path), `docs/../README.md` (traversal, contract deny with no bundle), binding mismatch in the PDP (`run_binding_mismatch`) and in the PEP (`task_ref_mismatch`) |
| Persisted evidence | `make local-evidence-trial EVIDENCE_DIR=ai-development-framework/docs/observability/evidence` | bundles already written by the adapter or by the Claude Code `Read` gate; no PDP, PEP, or runtime is called |

Prerequisites: `make install-dev` (fails closed with that hint if the packages do not import) and,
for the second source, the `Read` gate enabled as in [Read-only adapter](#read-only-adapter-p0).

The report is written to `docs/observability/trials/<trial_id>.json` (dir `0700`, file `0600`,
gitignored, never overwritten) with `schema_version`, `trial_id`, `created_at`, `source`
(`kind`, `suite_version`, `adapter_id`, `adapter_version`, `package_version`,
`latency_recorded`), `reads_total`, `bundles_total`, `reason_codes` (`outcome/reason_code` →
count), and `metrics` (the verified H4-01b `EvidenceTrialReport`). There is no content, path,
prompt, or raw argument; a reason code that does not match `^[a-z0-9_]+$` becomes
`deny/evidence_bundle_invalid` instead of being echoed.

How to read the main reason codes:

- `delivered/read_delivered` — read admitted, revalidated in the PEP, and delivered tainted.
- `deny/sensitive_path_denied` — admitted by the PDP, denied at the effect by the v1 policy. Counts in
  `admit_read_total` **and** in `sensitive_path_denied_total`; `deny_total` is only PDP denies.
- `deny/task_ref_mismatch`, `deny/workspace_binding_mismatch` — binding broken at the effect; they count
  in `binding_mismatch_total`.
- `deny/run_binding_mismatch` and other PDP denies that occur before scope — a bundle with
  `effective_scope: null`, verifiable; they count in `deny_total` and in the mapping category
  (`binding_mismatch_total`, `invalid_contract_total`). Trials before 2026-10-19 (WP1b)
  counted them in `evidence_bundle_invalid_total`: do not compare the two series directly.
- `deny/invalid_referenced_contract` — the request never validated; there is a read, there is no bundle
  (`reads_total − bundles_total`).
- `human_intervention_required_total` counts only bundles with `approval_required`, which the PDP
  does not emit today. It is not an approval flow.
- `latency_recorded: false` (persisted source): bundles do not carry latency; the
  `metrics.decision_latency_ms` block contains placeholder zeros and must be ignored.

Residual risks that the number does not cover: `Bash` and any other tool bypass the `Read` gate;
userspace is not a host sandbox; the two binding mismatch cases are injected by the suite (the
adapter does not change); the metrics are technical evidence from controlled runs, not compliance, ROI, or
proof of the absence of bypass.

## References

- ADR 0007 · [admission and enforcement boundary](architecture-decision-records/0007-runtime-and-tool-policy-boundary.md)
- ADR 0008 · [PEP and constrained local read runtime](architecture-decision-records/0008-pep-and-constrained-local-read-runtime.md)
- ADR 0009 · [local evidence integration](architecture-decision-records/0009-local-control-plane-evidence-integration.md)
- [Architecture and diagrams](ARCHITECTURE.md) · [Glossary](GLOSSARY.md) · [Roadmap](roadmap.md)
