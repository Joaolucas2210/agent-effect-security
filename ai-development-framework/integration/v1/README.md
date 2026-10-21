# H4-01 local evidence v1

`AdapterRequest` is a closed, structured envelope for H2-02/H3-01 objects. Its
`adapter_id` is declarative only: it cannot execute or authorize anything.

`EvidenceBundle` contains only redacted correlation metadata. It never contains a
prompt, read content, physical path/root, raw arguments, secret, credential, or
authorization grant. A denied PDP result has no read result or receipt (`null`).

All v1 digests are SHA-256 of UTF-8 JSON serialized with sorted keys and compact
separators (`json-c14n-v1`). `bundle_id` excludes itself and `bundle_sha256`;
`bundle_sha256` excludes only itself. `read_result_digest` covers the redacted
ReadResult projection (including taint and optional content hash, never content).

`verify_offline` consumes in-memory bundle/schema objects only. It validates the
closed Draft-07 contracts, receipt integrity, redacted bindings and these digests;
it neither replays a read nor grants authorization. `logical_replay` is likewise a
deterministic diagnostic projection of the already-recorded evidence.

Run the isolated local pilot with `make local-evidence-pilot`. It uses only the trusted
repository root and three internal revisions (`HEAD`, `HEAD~1`, `HEAD~2`); callers cannot
supply paths or revisions. Each trial receives its own snapshot and workspace, then emits
only the verified aggregate report. Failures use redacted stable codes. This is neither
H3-02 nor a process sandbox.

Workspace preparation reports only stable stage codes (revision, snapshot, worktree
prepare, cleanup, or prune); it never exposes Git diagnostics or filesystem details.

## P0-A: adapter attempt lifecycle

`AdapterAttemptEvent` 1.0 is an additive, closed contract. Each call reaching
`LocalReadAdapter.read` creates `_attempts/<opaque-id>.jsonl` in the host evidence
directory. `started` precedes validation/workspace preparation; `completed` follows
cleanup and records only the calculated result before return, a fixed reason code, optional bundle ID,
and cleanup outcome. Invalid run IDs become `null`; no raw inputs or content are kept.

Event SHA-256 hashes cover `{"domain":"adapter-attempt-event-v1","event":...}`
with the event's `event_sha256` excluded, using the existing `json-c14n-v1`.
The completion binds the start digest and the same attempt/adapter/run IDs.

`integration.adapter_attempt.verify_attempt(events, schema)` returns `complete`,
`incomplete` (start only), or `invalid`. It does not load files, execute a tool,
follow remote schema references, authenticate the issuer, or grant authority.
`complete` can mean `deny`; it verifies structure/integrity, not consumer delivery. Bundle verification
remains separate. A delivered receipt alone does not prove successful cleanup.

Journal creation/append failures prevent delivery (`attempt_evidence_failed`).
Interruption leaves an incomplete journal where persistence was possible. New
files/directories use 0600/0700; no resume or overwrite. Earlier gate rejections
are outside this adapter capture, and there is no cross-file/power-loss transaction.
Legacy trial ingestion reads `*.json`, leaving these `*.jsonl` records separate.
If final fsync and its ftruncate rollback both fail, a structurally complete journal
can retain calculated `delivered` while the adapter returns `deny` without content;
durability is unconfirmed. The payload is not a harness acknowledgement.
See [ADR 0010 proposal](../../docs/architecture-decision-records/0010-adapter-attempt-lifecycle.md).

## P0-B: pinned host read policy (opt-in)

The host configuration is a closed JSON object with exactly `schema_version: "1.0"`,
`profiles`, `policy`, and `context`. It reuses the existing ToolProfile, PolicyBundle
and PolicyContext v1 contracts. One profile and one operation are supported;
exact scopes, effect constraints, run ID and budget ceilings stay unchanged.

The host passes an absolute `host_policy_path` and a `host_policy_sha256` computed
as `digest(config)` using `json-c14n-v1`. Both are mandatory when either is set.
The adapter loads once, checks the outer pin, closed shape, nested schemas and
profile/policy hashes. Invalid configuration returns `host_policy_invalid` before
workspace preparation. A request copies the pinned artifacts without rehashing,
rewriting context or adding scope; PDP/PEP resolve authorization as before.

The gates obtain these values solely from `ADF_READ_POLICY_FILE` and
`ADF_READ_POLICY_SHA256`. Keep the pin fixed for the session, including across
fresh hook processes. Context run ID must match the harness session ID; requests
above a ceiling are denied, not silently clamped. Changing the file does not change
an existing adapter; a new instance with the old pin denies a changed configuration.

Both settings absent retain the reference demo that synthesizes grants from the
requested path. This compatibility mode is not an organizational policy. Environment,
artifact paths and pins are host trust inputs, not a sandbox against agents able to
alter their host. See [ADR 0011 proposal](../../docs/architecture-decision-records/0011-pinned-host-read-policy.md).

## P0-C: opt-in mediated read experiment

`integration.mcp_read_server.read_snapshot` exposes one local stdio MCP tool.
The host supplies the same pinned policy plus a fixed run ID. It returns only
the adapter's UTF-8 snapshot text after verifying the bundle and matching the
returned content's SHA-256 and byte count against its receipt. The optional
pinned `mcp[cli]` extra (see `requirements-test.txt`) supplies transport and tool schema. Tests connect in
memory and over actual stdio; existing native-tool hooks remain `gate_only`.
See [coverage matrix](../../docs/integrations/coverage-2026-09-29.md) and
[ADR 0012 proposal](../../docs/architecture-decision-records/0012-mediated-stdio-read.md).

## A2A edge (ADRs 0013/0014)

`a2a-agent-card.schema.json` and `a2a-request.schema.json` are closed subsets of the A2A
Agent Card and JSON-RPC request. The card is discovery only; the request can carry only
`skill` + `arguments.path`, so no credential, decision, bundle or grant fits in the body.

`CallerPrincipal` 1.0 (`caller-principal.schema.json`) is who asks, parallel to the unchanged
`ToolCallIntent` v1; only the gateway builds it after AuthN. `A2AEvidenceRecord` 1.0
(`a2a-evidence-record.schema.json`) links one authenticated request (principal, skill, outcome,
reason code) to its `EvidenceBundle` by `decision_id`/`bundle_id`; `record_id` is the canonical
SHA-256 of the record without itself. It holds no token and never authorizes. Additive v1 change:
`invalid_principal` and `principal_expired` join the attempt-event reason enum and the metric
mapping. See `integration/a2a_gateway.py` and `hooks/test-a2a-gateway.py`.

Delegation (ADR 0015) adds no contract: the `act` chain is validated (closed levels, acyclic,
depth <= 8) before the principal is built, delegated tokens are capped by the host's delegable
scopes, and `exchange_hs256` is a test-only RFC 8693-style double (narrower scopes, next-hop `aud`,
`exp` <= parent, actor appended).

Auth-required tasks (ADR 0016), additive: optional `message.taskId` (32 hex) in the request and
optional `task_id` in `A2AEvidenceRecord`. A task only correlates a resume with its paused attempt;
the resume is a full new admission and the task is consumed once.

RS256 over a host-pinned local JWKS (ADR 0017) adds `bearer_jwt_rs256` to
`CallerPrincipal.authn_method` (additive). Pin: absolute `ADF_A2A_JWKS_FILE` plus the SHA-256 of
its bytes in `ADF_A2A_JWKS_SHA256`; closed RSA entries only (n >= 2048, e = 65537, unique kid).
