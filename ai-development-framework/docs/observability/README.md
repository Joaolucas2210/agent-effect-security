# Observability

For installation into another repository, session-specific evidence directories,
agent hooks and repeatable trial capture, follow the [trial guide](../trials.md).
`make metrics` summarizes hand-off events; `local-evidence-trial` aggregates read bundles.
These are separate sources, not interchangeable measures of task success or productivity.

## Control-plane traces and A2A live trials

- **OTel export (ADR 0020):** off by default; `ADF_OTEL_ENABLED=1` sends one redacted
  `adf.a2a.request` span per A2A request to Jaeger ([`docker-compose.otel.yml`](docker-compose.otel.yml))
  or Langfuse ([`LANGFUSE.md`](LANGFUSE.md)). A trace is telemetry; the Evidence Bundle is the audit of record.
- **Live trials:** [`trials/a2a-live/`](trials/a2a-live/README.md) has real-HTTP runs with the case matrix,
  `verify_record` on the evidence, Jaeger screenshots, the terminal transcript and an OTel on/off benchmark.

`hooks/observability.sh` records one JSONL event for every archetype hand-off and creates a
task trajectory when that task ends. It deliberately runs locally: no provider SDK, service,
secret, PII, or guessed price is introduced.

## Record a hand-off

```bash
make observability-record TASK=issue-42 ARCHETYPE=Builder PHASE=build \
  TOKENS_IN=1200 TOKENS_OUT=800 BUDGET_REMAINING=5000 DURATION_SECONDS=42
make observability-complete TASK=issue-42 ARCHETYPE=Maintainer PHASE=review \
  TOKENS_IN=500 TOKENS_OUT=300 BUDGET_REMAINING=4200 DURATION_SECONDS=18 OUTCOME=success
```

`SWITCHED=true TRIGGER=security-risk` records a dynamic mode change. Token and cost values
are `na` unless the agent runtime exposes them (stored as JSON `null`); never invent provider pricing. `complete`
writes `trajectories/<task>.trajectory.md` from the structured source of truth,
`events.jsonl`.

## Read the health summary

```bash
make metrics
```

The summary reports recorded tokens, successful/failed-task and switch rates, supplied cost
estimate, and eval-run count. `make eval-agent-flow` also records its outcome here, linking
the existing eval result and trajectory evidence to the same operational history.

## H1-01: opt-in events for one existing eval gate

```bash
ADF_EVENTS_V1=1 RUN_ID=my-unique-run make eval-agent-flow CASE=sum-bug
ADF_EVENTS_V1=1 make eval-agent-flow CASE=median-bug  # UUID when RUN_ID is absent
ADF_EVENTS_V1=1 make eval-agent-flow-all             # one UUID per case; omit RUN_ID
make eval-agent-flow CASE=sum-bug                    # unchanged legacy path
```

Python 3.10+ is required only for instrumentation. Bash remains the entrypoint and executes
the existing `run_gate` and shared `project_case` functions. This measures a fixture gate,
not an agent run, model trial, task-success metric or isolated runtime. No new package is
required. `ADF` still selects the framework root; the legacy reader still uses `ADF_DIR`.

The two [v1 schemas](../../contracts/v1/) use JSON Schema draft-07 and `schema_version: "1.0"`.
The stdlib validator handles only these two shapes and four payloads, rejects unknown fields
and versions, and validates before writing. `null` is unknown, never zero. The tests generate
valid events plus invalid examples (missing fields, unknown status/version, wrong payload,
negative numbers, unsafe IDs). An optional independent draft-07 check runs if `jsonschema`
is already installed; otherwise that check is explicitly skipped, without installing it.

Each run exclusively creates `docs/observability/runs/<run_id>/events.jsonl` under the selected
ADF root. This directory is local/ignored. IDs must match `[A-Za-z0-9][A-Za-z0-9_.-]{0,127}`.
Repeated IDs fail without appending; an explicitly empty ID is invalid. `--all` with an explicit
RUN_ID fails before any case executes; omit it to generate an independent ID for each case.
CASE must identify an existing fixture and trajectory; traversal and symlink fixtures are refused.
The Make target exports CASE as data rather than interpolating it into shell source, so
metacharacters cannot execute before the runner validates the opt-in input.

Order: `run.started` → `gate.started` → actual test → `gate.finished` → existing CSV and legacy
completion → `run.completed`. Sequence starts at 1. UTC timestamps and monotonic durations are
separate. Tokens and cost remain null. Exactly one legacy completion is emitted, and CSV still
deduplicates by commit+case. Legacy readers do not consume v1 streams, so counts do not double.

| Result | GateResult | Completion | Runner exit |
| --- | --- | --- | --- |
| Test passed | pass, actual exit 0 | success | 0 |
| Test failed | fail, actual nonzero exit | failure | 1 |
| Fixture runtime absent | skipped / runtime_unavailable / exit_code null | skipped | 0, preserving the specified skip convention |
| Invalid input/schema or trace/projection write error | may have no final event | incomplete, never a successful completion | 2 |

These are runner exit codes. GNU Make reports recipe failures as its own exit 2, so invoke
`bash ai-development-framework/hooks/eval-agent-flow.sh CASE` when checking runner exits 1 vs 2.
Consumers must require a valid complete four-event stream and outcome success; exit 0 alone,
or a passing `gate.finished` without completion, is not success. No replay/resume is implemented.

`input_digest` hashes the fixture snapshot before the test: sorted relative POSIX filenames,
each encoded as UTF-8 name + NUL + lowercase SHA-256 of file bytes + newline, then SHA-256 of
that concatenation. Generated `__pycache__` files are excluded. No file contents or paths outside
the fixture are recorded. This is provenance of the input snapshot, not sandbox isolation or
protection against a hostile process mutating input during execution.

Run directories are created with mode 0700 and files 0600; directory-FD traversal refuses
symlinks. The writer verifies its file identity before each append. Failed appends roll back
only the attempted event, preserving all earlier events. Fixture stdout/stderr is discarded,
errors use fixed diagnostics, and environment/secrets/private reasoning are never serialized.
Caller-provided IDs should be opaque labels, not sensitive data. Fixtures remain trusted local
code: this slice does not restrict their own filesystem/network access. Legacy projection is
not a transaction with v1; if its write succeeds but completion fails, its record may remain.
The v1 run stays incomplete; reconcile manually, never replay or count it as success.

## H1-01 validation and rollback

```bash
bash ai-development-framework/hooks/test-run-events.sh
make quality
make eval
make eval-required BASE=f13e147
```

The self-test uses disposable Git repositories with an explicit test identity and independent
run directories. It tests pass/fail/skip, all four payloads, digest, IDs, symlinks, incomplete
streams, append/projection failures, sanitization, legacy readers, CSV and `--all`.

To disable v1 immediately, run `unset ADF_EVENTS_V1 RUN_ID` in the invoking shell (also remove
these overrides from the caller), then `make eval-agent-flow CASE=sum-bug`. This uses the legacy
path without changing any log. To revert the implementation, create a rollback branch and use
`git revert <H1-01-implementation-commit>` in a reviewed PR. Preserve the ignored run directory
locally; keep its ignore entry as a retention-only exception if reverting `.gitignore` would
expose it. Never stage, convert, delete or clean historical traces/CSV as part of rollback.
Do not use `git clean` or a hard reset. H1-02 and subsequent phases are not implemented here.
