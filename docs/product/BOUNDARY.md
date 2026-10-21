# Product boundary

**English** · [Português (Brasil)](BOUNDARY.pt-BR.md)

Updated: 2026-10-19 · Version 0.1.0 (experimental)

**Category:** *agent effect security*, a local control plane for coding agents. ADF decides whether an
effect requested by an agent may happen, enforces the decision at the moment of the effect, and leaves
evidence that can be verified offline. It is not an agent platform, an orchestration UI, a Langfuse
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

<a id="matriz-de-suporte"></a>
## Support matrix

Outside this table, assume **residual risk**: ADF neither sees nor blocks those paths.

| Edge | Covered surface | Validated version | AuthN modes | Not covered (residual) |
| --- | --- | --- | --- | --- |
| Claude Code | `PreToolUse` hook, `Read` matcher | Version not recorded in the trials (`na`): revalidate the payload format on the installed version | None (local process, trusted host) | `Bash`, `Grep`, `Glob`, third-party MCP, subagents with other tools |
| Codex CLI | `PreToolUse` `Bash` with a single allowlisted `cat <file>`; host activation through the same list as Claude (REQ-MP-01) | 0.157.0 (global hook: `na`) | None (local process) | `head`, `sed`, `rg`, `python -c`, pipes, redirections, any other command |
| A2A (HTTP) | `read_workspace_file` skill via `message/send` | This repo's gateway, HTTP only on `127.0.0.1` | HS256 (**pilot only**: whoever holds the secret can issue any token); RS256 with a JWKS pinned by SHA-256 (real IdP, no automatic rotation; [runbook](../../ai-development-framework/docs/runbooks/a2a-rs256-jwks.md)) | A stolen token is valid until `exp` (≤ 1 h; no DPoP/mTLS); public bind only through a host TLS proxy; tasks in memory |
| MCP stdio | Mediated read tool | Not validated on a real Claude/Codex client | None | Same as the row of the client that uses it |
| Cursor | — | No evidence adapter | — | Everything |

Vulnerabilities in the agent itself or in the IDE (permission bypass, vendor CVEs) are outside the
gate. ADF reduces what passes through the edges above; it does not make the agent secure.

## Evidence is the record; telemetry only visualizes

| Signal | Authority | Use |
| --- | --- | --- |
| `EvidenceBundle` + `A2AEvidenceRecord` (`verify_offline`, `verify_record`) | **Official record** | Audit, trial report, investigation |
| OTel spans (`adf.a2a.request`, `adf.local_read.request`) in Jaeger or Langfuse | None | Correlate by `record_id` / `bundle_id`; the span can be missing and is not signed |
| Agent trace in Langfuse | None | See what the agent attempted; it does not say what ADF allowed |

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
4. `make project-reasons` gives, per project, bundles, journal attempts (the root `.env`, denied by contract
   without a bundle, appears here) and counts per principal; with `POLICY=` it shows granted versus unused.
5. `make local-evidence-trial` aggregates bundles from the local adapter. It does **not** count A2A records
   (`evidence/_a2a/`). For the A2A edge, use the `summary.json` of the A2A trial.

| reason_code | Layer | Meaning |
| --- | --- | --- |
| `invalid_referenced_contract` | Contract v1 | Path outside the format (e.g., a root dotfile such as `.env`); no bundle |
| `invalid_scope` | PDP | `.env`/`.git` component or malformed scope |
| `scope_not_allowlisted` | PDP | Path outside the policy pinned by the host |
| `sensitive_path_denied` | Runtime | Admitted by the PDP, denied at the effect by the sensitive path policy |
| `run_binding_mismatch`, `task_ref_mismatch` | PDP / PEP | Decision used outside the run or snapshot it was bound to |
| `host_policy_invalid` | Adapter | Policy missing, partial, or with a wrong pin; never falls back to demo mode |
| `principal_required`, `principal_not_allowlisted`, `scope_not_allowlisted_for_principal` | PDP | Policy with `principal_rules` (ADR 0024): closed to anyone it does not name; each principal reads only its own list |

## Market themes (mapping, not certification)

| Theme | What ADF delivers | What it does not deliver |
| --- | --- | --- |
| Tool misuse (OWASP Agentic / LLM) | Reads only through PDP → PEP on the covered edges | Control of tools outside the edges |
| Excessive agency | Host-pinned policy, `read` effect only, byte budget, scopes per skill | Limits for effects that do not exist in the product |
| Runtime authorization outside the model | Deterministic decision without an LLM; read content marked `cannot_authorize` | Defense against prompt injection in general |
| Governance with an enforcement point | Deny + verifiable evidence per decision | Dashboard, SSO/RBAC, compliance reports |

This is not a claim of conformance with OWASP or with any framework.
