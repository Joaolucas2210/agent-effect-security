# ADR 0029: delivery mode in evidence

- **Status:** Accepted — human acceptance on 2026-11-04 (maintainer, with the wave-2 approval); previously Proposed. Implemented the same day; see *Implementation note*.
- **Date:** 2026-11-04
- **Depends on:** ADRs 0009, 0012 (Accepted), 0026.
- **Scope:** `EvidenceBundle` and `RuntimeAuditReceipt` schemas, additive.
- **Threats:** THR-05 (evidence over-claim).

## Problem

On Claude `Read` and Codex `cat` the hook decides and the native tool delivers bytes from the live checkout;
on the MCP stdio server ADF delivers the snapshot bytes (ADR 0012). The bundle looks identical in both cases.
A reader of a trial report cannot tell whether the content digest proves what the model saw.

## Decision

- `delivery_mode: "gate_only" | "mediated"` becomes required in `RuntimeAuditReceipt` 1.1 and is projected
  into `EvidenceBundle` 1.1. `verify_offline` rejects a 1.1 bundle without it; 1.0 bundles stay valid and are
  reported as `delivery_mode: unknown` by the aggregator.
- `content_sha256` in a `gate_only` receipt is documented as the snapshot digest, never the delivered bytes.
- `evidence_trial_metrics` splits `admit_read_total` by mode; `make project-reasons` prints both.

## Implementation note (2026-11-04)

`delivery_mode` lives in the **bundle** (not the receipt): the runtime that writes the receipt does not know
which edge is calling; the caller of the adapter does. `EvidenceBundle` schema gains `1.1` with
`delivery_mode` required, and `1.0` forbids the field (both in the schema's `if/then/else` and in
`verify_offline`). The field sits under `bundle_id`/`bundle_sha256`, so flipping it invalidates the bundle.
`LocalReadAdapter.read(..., delivery_mode=None)` keeps 1.0 byte-identical; `read_gate_host.read_adapter`
defaults to `gate_only` (the weaker claim), the MCP stdio tool and the A2A gateway pass `mediated` because
they return the bytes. `adf verify` prints `delivery_mode=`; `make project-reasons` counts
`delivery_mode:<mode>=` per project. The fixed-suite trial runner still produces 1.0 bundles (no edge), so its
pinned metrics do not change. Metrics split in `evidence_trial_metrics` is deferred: the observation schema
is versioned and pinned by the normative oracle; it moves when a partner needs the split.

## Options considered

1. **Document only** (status quo in CONTROL_PLANE.md) — rejected, the bundle must be self-describing offline.
2. **Make every edge mediated** — changes the agent's native tools, latency, and the ADR 0012 residual; rejected for now.

## Consequences

- Positive: claim C5 (ADR 0026) is verifiable from the bundle alone.
- Negative: a schema bump; pinned suite counts change once (document as in WP1b).
- Reversibility: cheap.

## Residual risks

`gate_only` remains the common case; the label is honest, not a fix.

## Rollback

Drop the field from the 1.1 schema; 1.0 verification is untouched.
