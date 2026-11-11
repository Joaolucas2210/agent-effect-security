# Public contracts

**English** · [Português (Brasil)](PUBLIC-CONTRACTS.pt-BR.md)

What an integrator can rely on in ADF `0.2.0`, how each surface is versioned, how it fails, and which test holds it.
Everything here runs on the host: **no remote endpoint, no control plane service, no SaaS.** The A2A edge listens on
loopback only. What each edge does not cover is in [BOUNDARY's support matrix](BOUNDARY.md#support-matrix); the
claims ADF makes are only those of [ADR 0026](../../ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md).

## Compatibility policy

- The project follows [Semantic Versioning](https://semver.org/). While the version is `0.x`, **a minor release may
  change a contract**; the [CHANGELOG](../../CHANGELOG.md) entry says so when it does. A patch release does not.
- A contract is versioned by the field inside the document (`schema_version`, `decision_version`, `result_version`,
  `policy_version`, `protocolVersion`), not by the package version. A reader must reject a version it does not know.
- Every JSON schema below is closed (`additionalProperties: false`), so an unknown field is an error, not an
  extension point.
- **Stability levels used in this document:**
  - **Versioned**: changes only with a new version value or a CHANGELOG-announced `0.x` minor.
  - **Experimental**: may change or disappear in any release. Everything that rests on an ADR with status
    *Proposed* is experimental. **A Proposed ADR is not a stable contract.**

## JSON schemas

Draft-07 JSON Schema files in the source clone. Stability: **versioned**.

| Directory | Schemas | `$id` form | Version field (value) |
| --- | --- | --- | --- |
| `tools/v1/schemas/` | tool-profile, tool-call-intent, policy-bundle, policy-context, admission-decision, list-files-input, decision-signal, typed-question | `https://agent-flow.invalid/tools/v1/schemas/<name>.schema.json` | `policy_version` / `decision_version` `1.0`; `schema_version` `1.0` on decision-signal and typed-question |
| `runtime/v1/schemas/` | runtime-workspace-descriptor, runtime-audit-receipt, read-result, sensitive-path-policy-v1 | `https://agent-flow.invalid/runtime/v1/schemas/<name>.schema.json` | `result_version` `1.0` on read-result |
| `integration/v1/schemas/` | adapter-request, evidence-bundle, adapter-attempt-event, caller-principal, a2a-evidence-record, a2a-request, a2a-agent-card, evidence-trial-observation, evidence-trial-report | bare file name (e.g. `evidence-bundle.schema.json`); adapter-attempt-event uses `https://agent-flow.invalid/integration/v1/…` | `schema_version` `1.0`; evidence-bundle `1.0` or `1.1` |
| `integration/v2/schemas/` | attempt-timing, session-trial-report, task-evaluation | `https://agent-flow.invalid/integration/v2/…`; task-evaluation `urn:adf:task-evaluation:1.0` | `schema_version` `1.0`; session-trial-report `2.0` |
| `contracts/v1/` | context-item, eval-result, gate-result, run-config, run-event, task-spec, tool-capability (development harness, not the read path) | see each file | see each file |

- `$id` values under `agent-flow.invalid` are identifiers, not URLs: nothing is fetched.
- Evidence: the example and negative fixtures under each `*/v1/examples` and `*/v1/tests`; `hooks/test-local-read-adapter.sh`,
  `hooks/test-a2a-gateway.sh`, `hooks/test-tool-admission.sh`, `hooks/test-runtime-read.sh`.

## Reason codes

- **Shape**: every `reason_code` / `stable_reason_code` matches `^[a-z0-9_]+$` and is stable text, safe to branch on.
  A reason code never carries a path, content or a credential.
- **Enumerated**: the closed list is in `integration/v1/schemas/adapter-attempt-event.schema.json`
  (`payload.reason_code` enum). Codes elsewhere use the pattern only; the schema of the record that carries them is the
  contract.
- **Common codes**: `host_policy_invalid` (no valid pinned policy), `scope_not_allowlisted`, `invalid_scope`,
  `sensitive_path_denied`, `adapter_failed`, `evidence_signing_unavailable`, `attempt_evidence_failed`,
  `control_plane_tampered`, `unsupported_tool`, `unexpected_tool_input`.
- Compatibility: adding a code is a `0.x` minor change; renaming or removing one is announced in the CHANGELOG.

## Evidence

Stability: **versioned**. Evidence is written on the host and verified offline; nothing is sent anywhere.

| Artifact | Location | Version | Verify |
| --- | --- | --- | --- |
| EvidenceBundle | `<evidence_dir>/<run_id>/<bundle_id>.json` (0600, exclusive create) | `1.0`, or `1.1` with `delivery_mode` = `mediated` \| `gate_only` ([ADR 0029](../../ai-development-framework/docs/architecture-decision-records/0029-delivery-mode-in-evidence.md)) | `adf verify FILE` (`verify_offline`) |
| A2AEvidenceRecord | `<evidence_dir>/_a2a/<record_id>.json` | `1.0` | `adf verify FILE` (also checks the linked bundle) |
| Attempt journal | `<evidence_dir>/_attempts/<attempt_id>.jsonl` | adapter-attempt-event `1.0` | schema |
| HMAC signature | `<file>.sig` next to the file, when a host key is configured ([ADR 0030](../../ai-development-framework/docs/architecture-decision-records/0030-evidence-authenticity-host-key.md)) | — | `adf verify FILE --key KEYFILE` |

- `delivery_mode` says what the bundle proves: `mediated`, ADF returned the snapshot bytes; `gate_only`, the native
  tool read the file and the bundle proves the decision and a confined snapshot read, not the bytes delivered (claim C5).
- Signatures are shared-secret HMAC: they show integrity to whoever holds the host key, not public authenticity.
- Evidence: `hooks/test-local-evidence-bundle.sh`, `hooks/test-delivery-mode.sh`, `hooks/test-evidence-signing.sh`,
  `hooks/test-a2a-gateway.sh`.

## Hook I/O

The `PreToolUse` hook for Claude Code and Codex (`adf hook`, registered with `adf hook-snippet`). Stability:
**versioned** for the output shape; the set of gated tools grows per ADR.

- **Input** (JSON on stdin), fields read: `hook_event_name` (must be `PreToolUse`), `tool_name`, `tool_input`
  (`file_path` for `Read`; `command`, optional `workdir` for `Bash`; the path or command field of the deny-only tools),
  `session_id` (run id), `cwd` (Codex project root), `agent_type` (Claude subagent, [ADR 0033](../../ai-development-framework/docs/architecture-decision-records/0033-subagent-principal-propagation.md)).
  The project root also comes from `CLAUDE_PROJECT_DIR`. Unknown `tool_input` keys deny with `unexpected_tool_input`.
- **Output** (JSON on stdout, exit 0):
  `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"|"deny", "permissionDecisionReason": "adf: <outcome>/<reason_code>[ bundle=<id>]"}}`.
  Deny-only gates never answer `allow`.
- **No decision**: exit 0 with **empty stdout**. The agent's normal permissions apply. This happens when the project
  is not listed in `$ADF_HOME/enabled-projects`, the tool has no gate, the hook's executable or scripts are missing
  (for example a wheel-only install), or an error occurs before ADF knows the project is enabled.
- **Enabled project + any failure = deny** (`adapter_failed`, `host_configuration_invalid`, `control_plane_tampered`, …).
- Evidence: `hooks/test-adf-read-hook.sh`, `hooks/test-bootstrap-matrix.sh`, `hooks/test-deny-gate-journal.sh`;
  failure contract in [ADR 0037](../../ai-development-framework/docs/architecture-decision-records/0037-hook-bootstrap-failure-contract.md).

## CLI

`adf` ([ADR 0025](../../ai-development-framework/docs/architecture-decision-records/0025-adf-operator-cli.md)).
Stability: **versioned** for command names and exit codes; human-readable stdout lines may change.

| Command | Exit codes |
| --- | --- |
| `adf doctor` | 0 control plane intact; 1 tampered (or MCP drift); **3 not pinned** (never green). The read-policy line is diagnostic and does not change the code |
| `adf verify FILE [--key KEYFILE]` | 0 verified; 1 not verified; 2 unusable input or key |
| `adf key init [KEYFILE]` | 0 created; 1 exists (never overwritten) |
| `adf mcp pin FILE` | 0 pin printed; 1 registry rejected |
| `adf mcp probe FILE [--write]` | 0 unchanged; 1 changed, unpinned or unreachable (with `--write`: 1 only when unreachable); 2 registry rejected |
| `adf hook` | always 0 (see [Hook I/O](#hook-io)) |
| `adf hook-snippet`, `adf version` | 0 |
| `adf projects …`, `adf policy build …` | the underlying script's codes; 2 when run from a wheel without the clone |
| `adf a2a serve` / `adf a2a mint` | 2 on usage error or invalid host settings |
| unknown command | 2 (usage) |

## A2A edge

`adf a2a serve` ([ADRs 0013–0019](../../ai-development-framework/docs/architecture-decision-records/0013-a2a-edge-authn-authz.md), 0022).
Stability: **versioned**; client rules in [BOUNDARY](BOUNDARY.md#a2a-client-contract).

- **Transport**: HTTP on `127.0.0.1` only (any other bind address is refused); TLS, if needed, is a local proxy.
  Body at most 64 KiB.
- **Discovery**: `GET /.well-known/agent-card.json`, `protocolVersion` `0.3.0`. The public card lists no
  scope-protected skill; `agent/getAuthenticatedExtendedCard` returns the full card after AuthN.
- **JSON-RPC 2.0 on `POST /`**, closed request schema (`a2a-request.schema.json`): `message/send` with one data part
  `{"skill": "read_workspace_file", "arguments": {"path": …}}` and an optional `taskId`.
- **AuthN**: `Authorization: Bearer <JWT>`, RS256 over a pinned JWKS or the HS256 pilot secret; `iss`, `aud`, `exp`,
  `nbf`, lifetime ≤ 3600 s, delegation chain `act` ≤ 8.
- **Error model**:
  - 200: the PDP/PEP decided. `result.outcome` is `delivered` or `deny`; **200 does not mean delivered**.
    `result.task.status.state` is `auth-required`, `input-required`, `completed` or `failed` when a task exists.
  - 400 `parse_error` (-32700), `invalid_request`, `credential_in_payload` (-32600).
  - 401 AuthN (-32001), 403 skill/scope (-32003), 409 task (-32006), 500 `a2a_evidence_failed` (-32005),
    503 `host_policy_invalid` (-32004).
  - Transport only (not JSON-RPC): 404, 411, 413.
- **Host policy**: read once, when the gateway starts, from the pinned file (`ADF_READ_POLICY_FILE` +
  `ADF_READ_POLICY_SHA256`) and checked against the pin and the schemas. Without a valid pinned policy the gateway
  still serves the card but answers every read with 503 `host_policy_invalid`; **it never uses the reference demo
  policy**. A policy edited on disk takes effect only after a restart, and only if the pin matches.
- Evidence: `hooks/test-a2a-gateway.sh`, `hooks/test-a2a-policy-source.sh`, `hooks/test-mcp-a2a-client.sh`,
  `hooks/test-a2a-live-trial.sh`.

## Python extension seam: `PolicySource`

Stability: **experimental**. It rests on [ADR 0039](../../ai-development-framework/docs/architecture-decision-records/0039-community-extension-seams.md),
which is **Proposed**; the signature may change or be removed.

- `integration.extensions.PolicySource`: a `typing.Protocol` with `load() -> (config, sha256_pin) | None`.
  The default is `HostPolicyFile(path, sha256)`, the same file + pin as the environment variables.
- Accepted by `LocalReadAdapter(..., policy_source=)` and `A2AGateway(..., policy_source=)` (keyword only, with the
  path/pin pair set to `None`). Selection is by constructor argument only: no environment variable, entry point or
  registry selects a source.
- Whatever a source returns is deep-copied and re-checked against its pin, the envelope and the contract schemas. A
  source that raises or returns anything off-contract denies every read with `host_policy_invalid`.
- `None` selects the reference demo **in the adapter only**; the A2A gateway refuses it (503).
- The source is consulted once, at construction. There is no reload.
- Evidence: `hooks/test-extension-contracts.sh`, `hooks/test-a2a-policy-source.sh`.

## Not a contract

- Anything under a Proposed ADR (for example typed host configuration, ADR 0040), internal module functions not named
  above, log lines on stderr, OpenTelemetry span attributes (a view, not evidence), file names under `hooks/`.
- Real-client behaviour beyond what [COMPATIBILITY](COMPATIBILITY.md) records.
