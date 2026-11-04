# Product boundary

**English** · [Português (Brasil)](BOUNDARY.pt-BR.md)

Updated: 2026-11-04 · Checkout version 0.1.0 (experimental)

**Category:** *agent effect security*, a local control plane for coding agents. At a supported, installed edge,
ADF decides whether an observed read may proceed and, when the request reaches composition, leaves a bundle
that can be checked offline. Earlier denies can leave a journal entry instead. It is not an agent platform, an orchestration UI, a Langfuse
replacement, an MCP marketplace, an operating system sandbox, or a certification factory.

```text
Intent → AuthN (edges) → scope/skill → PDP → PEP → minimal-effect runtime → Evidence
```

## Supported effects

| Effect class | Status | Where the rule lives |
| --- | --- | --- |
| `read` (regular file, Git snapshot prepared by the host) | **Supported** | ADRs 0007, 0008, 0011 |
| `write`, `network`, `destructive`, `secrets` | **Not supported.** The PDP denies with `effect_not_supported_in_h2_02` | Requires its own `Accepted` ADR + design partner demand recorded in the [plan](IMPLEMENTATION_PLAN.md) |

## Host activation

Host activation is not a monorepo installation: one ADF clone and one global hook serve N projects,
each enabled in a host list (`~/.adf/enabled-projects`, operated by `make projects` /
`project-enable` / `project-disable`); outside that list ADF decides nothing. `make project-reasons`
aggregates the `reason_code` values per project from `~/.adf/evidence`, counts only.
Step by step in [trials.md](../../ai-development-framework/docs/trials.md#many-projects-one-hook-req-mp-01).

## Bootstrap and host trust

`adf hook-snippet` prints registration JSON; the operator must merge it into the client settings, restart the
client and then pin the installed control plane. The emitted wrapper contains `[ -x "$A" ] || exit 0`: if the
executable is missing, no ADF decision is returned. `integration/cli.py` also returns 0 without a decision on an
unexpected `adf hook` exception. The enabled-project dispatcher returns a deny for failures it catches *after*
it has identified the enabled project. These facts do not establish client-wide fail-closed behavior. A missing
registration, a failed wrapper, an unobserved tool, or a client that ignores hook output can proceed under the
client's own rules. [ADR 0037](../../ai-development-framework/docs/architecture-decision-records/0037-hook-bootstrap-failure-contract.md)
records the open design and the client-version tests required before any semantic change.

<a id="matriz-de-suporte"></a>
## Support matrix

Outside this table, assume **residual risk**: ADF neither sees nor blocks those paths.

| Edge | Covered surface | Validated version | AuthN modes | Not covered (residual) |
| --- | --- | --- | --- | --- |
| Claude Code | `PreToolUse` hook, `Read` matcher; deny-only on `Grep`/`Glob` (sensitive paths), `Edit`/`Write`/`MultiEdit`/`NotebookEdit` (sensitive + agent-config paths) and `WebFetch`/`curl`/`wget` after a sensitive attempt in the same session (ADR 0028 slices 1a, 1c); observed deny-only decisions are journaled when persistence succeeds | Version not recorded in the trials (`na`): revalidate the payload format on the installed version | None (local process, trusted host) | Bash shapes outside the 1b grammar, `Grep`/`Glob` without `path`, MCP servers outside the registry, subagents with other tools; deny-only gates leave a journal entry, never a bundle |
| Codex CLI | `PreToolUse` `Bash`: a single allowlisted `cat <file>` is admitted with a bundle; listed `head`/`tail`/`sed`/`grep`/`rg`/`awk`/… reads on sensitive paths and selected ambiguous command shapes are denied (ADR 0028 slice 1b); `curl`/`wget` after a sensitive attempt denied (1c); host activation through the same list as Claude (REQ-MP-01) | 0.157.0 (global hook: `na`) | None (local process) | Scripts invoked by name, interpreter APIs outside the closed grammar, unlisted read-equivalent binaries and non-read commands; [fixture test](../../ai-development-framework/hooks/test-bash-read-grammar.py) confirms some return no ADF decision |
| A2A (HTTP) | `read_workspace_file` skill via `message/send` | This repo's gateway, HTTP only on `127.0.0.1` | HS256 (**pilot only**: whoever holds the secret can issue any token); RS256 with a JWKS pinned by SHA-256 (real IdP, no automatic rotation; [runbook](../../ai-development-framework/docs/runbooks/a2a-rs256-jwks.md)) | A stolen token is valid until `exp` (≤ 1 h; no DPoP/mTLS); public bind only through a host TLS proxy; tasks in memory |
| MCP (any server, Claude Code) | Deny-only: server and tool names must be in the host-pinned registry; a pinned `definition` (command/args/env keys) must match every Claude Code config scope at call time; tool-list digest checked offline by `adf mcp probe` (ADR 0031 slices 1–2); tools the host declares `write`/`network` are denied once the session attempted a sensitive path; descriptions authorize nothing | Probe validated against this repo's own stdio server; real third-party clients `na` | None | Rug-pull between probes (`adf doctor` fails once the last probe is older than the host's limit, 30 days by default); Codex `config.toml` drift only reported by `adf doctor` (Codex sends no MCP calls to the hook); servers started outside the hook path; the server's own output (tainted, not blocked) |
| MCP stdio | Mediated read tool | Not validated on a real Claude/Codex client | None | Same as the row of the client that uses it |
| Cursor | — | No evidence adapter | — | Everything |

Vulnerabilities in the agent itself or in the IDE (permission bypass, vendor CVEs) are outside the
gate. ADF reduces what passes through the edges above; it does not make the agent secure.

## Evidence is the record; telemetry only visualizes

| Signal | Authority | Use |
| --- | --- | --- |
| `EvidenceBundle` + `A2AEvidenceRecord` (`verify_offline`, `verify_record`) | Composed decision record | Audit, trial report, investigation; `gate_only` proves the decision and snapshot check, not native delivered bytes; `mediated` returns controlled bytes |
| Attempt journal (`_attempts/`) | Pre-adapter / deny-only attempt record | Reason and principal for an observed attempt; no bundle or read receipt is implied |
| OTel spans (`adf.a2a.request`, `adf.local_read.request`) in Jaeger or Langfuse | None | Correlate by `record_id` / `bundle_id`; the span can be missing and is not signed |
| Agent trace in Langfuse | None | See what the agent attempted; it does not say what ADF allowed |

`adf verify FILE` checks schema, digests and bindings but reports `authenticity=not_checked`. With `--key`, it
checks the detached HMAC sidecar using the host's shared secret. That is host-key authenticity, not a public
signature or proof to an independent auditor. Do not distribute the HMAC key. Signing is opt-in; an unsigned
bundle can still pass integrity checks. Evidence may contain repository-relative scopes and IDs; review before
sharing. [ADR 0030](../../ai-development-framework/docs/architecture-decision-records/0030-evidence-authenticity-host-key.md)
defines the implemented scheme; [ADR 0038](../../ai-development-framework/docs/architecture-decision-records/0038-evidence-key-lifecycle.md)
records the unresolved rotation and third-party verification design.

## A2A client contract

- **HTTP 200 does not mean the read was delivered.** A PDP/PEP decision comes back as 200 with
  `result.outcome = "deny"` and a `reason_code`. The client must read `result.outcome`.
- 401 is an AuthN failure (no record: there is no identity); 403 is skill/scope; 400 is a request outside
  the schema; 409 is an invalid task; 500 `a2a_evidence_failed` means there was no verifiable evidence, so
  no byte left.
- Example: `config/.env` is denied by the PDP (`invalid_scope`) before any scope exists. The bundle has
  `effective_scope: null` and verifies offline, and the edge responds 200 with `outcome=deny` and a record.
  Until 2026-10-19 this case responded 500 (WP1b of the [plan](IMPLEMENTATION_PLAN.md)).

## How AppSec uses the trial reports

1. Run the suite at the pinned SHA and keep the aggregate, not the raw bundles (they can contain file names).
2. Read the `reason_codes`, not only the deny total. `deny_total` counts only PDP denies; denies at the
   effect appear in `sensitive_path_denied_total` and `binding_mismatch_total`.
3. Require `verify_offline` or `verify_record` on a sample: a number without a verifiable bundle is not proof.
4. `make project-reasons` gives, per project, bundles and journal attempts (for example an invalid traversal
   denied by contract without a bundle) and counts per principal; with `POLICY=` it shows granted versus unused.
   Since ADR 0036, a root `.env` reaches the PDP and produces a bundle for its `invalid_scope` denial.
5. `make local-evidence-trial` aggregates bundles from the local adapter. It does **not** count A2A records
   (`evidence/_a2a/`). For the A2A edge, use the `summary.json` of the A2A trial.

| reason_code | Layer | Meaning |
| --- | --- | --- |
| `invalid_referenced_contract` | Contract v1 | Path outside the format (`..`, `//`, NUL, shell metacharacters); no bundle. Since ADR 0036 a root dotfile is a valid path: `.env` is a PDP deny **with** a bundle |
| `invalid_scope` | PDP | `.env`/`.git` component (root or nested) or malformed scope |
| `scope_not_allowlisted` | PDP | Path outside the policy pinned by the host |
| `sensitive_path_denied` | Runtime | Admitted by the PDP, denied at the effect by the sensitive path policy |
| `run_binding_mismatch`, `task_ref_mismatch` | PDP / PEP | Decision used outside the run or snapshot it was bound to |
| `host_policy_invalid` | Adapter | Policy missing, partial, or with a wrong pin; never falls back to demo mode |
| `principal_required`, `principal_not_allowlisted`, `scope_not_allowlisted_for_principal` | PDP | Policy with `principal_rules` (ADR 0024): closed to anyone it does not name; each principal reads only its own list |

## Market themes (mapping, not certification)

| Theme | What ADF delivers | What it does not deliver |
| --- | --- | --- |
| Tool misuse (OWASP Agentic / LLM) | Admitted reads traverse PDP → PEP on covered edges; selected other attempts meet deny-only gates | Control of tools outside the edges |
| Excessive agency | Host-pinned policy, `read` effect only, byte budget, scopes per skill | Limits for effects that do not exist in the product |
| Runtime authorization outside the model | Deterministic decision without an LLM; read content marked `cannot_authorize` | Defense against prompt injection in general |
| Governance with an enforcement point | A composed read decision has a bundle; earlier observed denies have a journal entry | Dashboard, SSO/RBAC, compliance reports |

This is not a claim of conformance with OWASP or with any framework.

Attacker model, trust boundary and the only claims allowed in public text:
[ADR 0026](../../ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md)
(Accepted). Real incidents mapped to `covered | residual | out_of_scope`: [coverage map](../knowledge/coverage.md).
