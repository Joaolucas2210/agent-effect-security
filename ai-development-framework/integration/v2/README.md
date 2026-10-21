# P0-D session report v2

`SessionTrialReport` 2.0 is a redacted projection of P0-A attempt journals and
H4-01 evidence bundles. It is separate from the H4-01b v1 trial report; no v1
hash, reader or schema changes. Its verifier checks a closed schema, digest,
and counting invariants, not authorization. A valid `started` event contributes
one observed attempt; an incomplete or invalid completion is not a task result.
Valid bundles without a correlated attempt are counted as orphans.
The shared `_attempts` directory can contain several sessions. Fully verified
foreign journals count as `journal_other_session_total`; a foreign start with
invalid completion bindings remains invalid evidence. Repeated session attempt
IDs count as `journal_duplicates_total`, without adding observed attempts.
Conflicting copies invalidate that attempt's capture regardless of file order.
Repeated verified bundles count as `bundle_duplicates_total`, without adding
decisions. Invalid copies remain invalid even if a valid copy was already seen.

New reports include optional `decisions` counters over distinct verified bundles,
including orphans: PDP `admit_read`, `deny`, `approval_required`, and runtime
`delivered`/`deny`. `approval_required` is retained from the v1 bundle contract;
this collector does not enable approvals or change the PDP. A delivered receipt
is not a task result or proof of adapter return after cleanup.

The three new artifact counters and `decisions` are additive, optional fields
of v2.0, covered by its report hash. Older reports still verify: absent artifact
counters contribute zero to invariants; missing decisions remain unknown.
Existing reports are not rewritten or reclassified. In older reports,
`*_invalid_total` may include duplicates and foreign journals. Regenerate from
original evidence to obtain the new classification, using a new trial ID.
When multiple attempts reference the same bundle, every reference is a conflict;
none establishes a verified correlation. Previously generated v2 reports with
one verified reference in such a conflict must be regenerated from the original
evidence. The v1 artifacts remain unchanged.

The collector opens entries without blocking and accepts only regular files.
FIFOs, symlinks and other unsupported entries count as invalid artifacts.

The collector reads a closed, host-selected session directory. Old journals and
bundles contain no monotonic timings: their observations remain unmeasured.
`task_outcome` is `null` until an external evaluator supplies a reproducible task result.
No read content, prompt or physical path is copied into the report. The host
must review metadata before sharing it; same-UID processes are outside this
local artifact boundary.

See [P0-D spec](../../../docs/specs/p0d-trial-sessions.md) and the
[trial guide](../../docs/trials.md).
The [normative oracle](tests/session-trial-normative-oracle.json) and
`examples/session-trial-report.json` cover legacy compatibility, counted artifacts,
measured zero, negative duration, forbidden content and self-hashed bad counts.

## Host-declared trial provenance

New reports may include the optional, closed `provenance` object with
`agent_name` (`claude`, `codex`, `cursor`, `other`), `agent_version` (a path-free
identifier), `revision_sha` (full 40-character lowercase Git SHA), and
`acceptance_sha256` (SHA-256 of the externally retained acceptance document or
test bytes). All four fields are required when the object is supplied; absence
means unknown. The report digest covers them, and older v2 reports still verify.
The collector does not attest these host declarations or execute acceptance
tests. They neither authorize reads nor establish task success; `task_outcome`
remains `null`. Do not copy task text, prompts or paths into metadata. See the
[capture commands](../../docs/trials.md#registrar-proveniência-do-trial).

## Monotonic timings (P0-D step 3, opt-in)

The host sets `ADF_CAPTURE_TIMINGS=1` before starting Claude, Codex or the MCP
stdio server. Their integrations call `read_observed`, which times
`LocalReadAdapter.read` and exports a separate owner-only `_timings/<attempt_id>.json`
after the adapter returns or raises. The observer binds the record to the
verified journal's `attempt_id`, `run_id` and started-event hash. Neither the
agent payload nor a timing record can authorize a read. PDP/PEP, v1 schemas,
hashes and delivered content are unchanged. `compose` accepts a host-owned
decision callable solely to wrap the existing PDP at its call boundary; it
contains no clock or telemetry. Runtime timing wraps the owned runtime instance,
without modifying its class or other calls.

`AdapterAttemptTiming` 1.0 has a closed [schema](schemas/attempt-timing.schema.json),
[oracle](tests/attempt-timing-normative-oracle.json), domain-separated digest,
fixed clock/unit/boundary provenance and `returned`/`raised` capture states.
Those states do not describe task success, client receipt or model consumption.

| Stage | Boundary |
| --- | --- |
| `prepare` | `WorkspaceManager.prepare` |
| `decision` | The existing PDP `decide` call, excluding request validation and PEP |
| `read` | `LocalReadRuntime.read`, excluding PEP validation and receipt construction |
| `persistence` | Sum of journal creation/start, bundle persistence and journal completion spans |
| `cleanup` | `WorkspaceManager.cleanup`, including failure |
| `total` | Host observation of adapter entry until `read` returns or raises, including journal close |

Stages use `time.monotonic_ns`; milliseconds are rounded down once per stage.
Nonexecuted stages are `null`; a real sub-millisecond measurement is `0`.
Nested stages are never added to manufacture `total`. Observation serialization,
fsync/export, host-hook overhead and MCP transport/model time are outside the
adapter span. Export failure emits only `adf: timing_evidence_failed` to stderr,
does not change a read result or exception, and leaves coverage unproven. A
journal start that failed to persist has no binding and produces no timing file.
Exported files use exclusive creation, owner-only permissions and directory
handles without following symlinks. A failed export can leave a truncated
artifact, which the collector rejects; no retry overwrites it.

The v2 report adds optional `timings` capture counts, stage summaries and
`observations[].timing` with the verified source record. Correlation requires a
matching verified start; conflicts or invalid journal captures cannot contribute
samples. A fully verified record from another session counts separately.
Duplicate record hashes add no sample; different records for the same attempt
are all conflicts. Valid records without a correlatable attempt count as
`uncorrelated_total`, without inventing attempts. Invalid artifacts count as
`invalid_total`; missing `_timings` is unknown coverage.

Each stage summary reports `count`, `sum`, `min` and `max` over non-null,
correlated samples only. No percentiles are inferred. The original top-level
`durations_ms` remains `null`: attempt sums are not session wall time. Earlier
v2 reports still verify and are never rewritten; absent `timings` means unknown.
Disable `ADF_CAPTURE_TIMINGS` to revert to the existing integration behavior;
existing v1 and v2 evidence remains readable.

## External task evaluation

`task-evaluation.schema.json` is a separate **1.0** assessment contract. It does
not change session-report v2 or v1 evidence. `integration.task_evaluation`
provides `build_task_evaluation(report, ...)` and
`verify_task_evaluation(record, report)`; the session must verify and include
complete provenance. The record binds its trial, task, session, report digest,
acceptance digest and initial revision. The evaluated revision may differ.

The external assessor declares `success`, `failure` or `skipped`. Executed
assessments require a SHA-256 digest of the external result artifact; skipped
assessments require `result_sha256: null`. Hash the exact bytes of that artifact
with SHA-256 and retain it privately alongside the acceptance criterion. The
builder accepts the digest, never executes checks or reads the artifact.
Identifier fields contain labels rather than reviewer identities, paths or logs.

The domain-separated evaluation digest protects integrity and session binding.
It does not authenticate the assessor, establish that checks ran, or prove the
declared outcome. Consumers must verify the external result and acceptance
criterion independently. Session `task_outcome` remains `null`; an assessment
is consumed as a separate record. Legacy sessions without provenance remain
valid sessions and cannot acquire an evaluation through this API.
