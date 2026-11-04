# ADR 0033: subagent principal propagation on local edges

- **Status:** Accepted — human acceptance on 2026-11-04 (maintainer); previously Proposed. Implemented the same day; see *Implementation note*.
- **Date:** 2026-11-04
- **Depends on:** ADRs 0015, 0023, 0024 (Accepted), 0026.
- **Scope:** `CallerPrincipal` for local edges when the harness spawns subagents. No new effect.
- **Threats:** OWASP ASI07 inter-agent trust; THR-01.

## Problem

A2A carries a verified-shape `act` chain with depth ≤ 8. Locally the principal is `claude:<agent_type>` and
every subagent shares the parent's `session_id` as `run_id`. Evidence cannot say which subagent, at which
depth, read a path, and `principal_rules` cannot distinguish a fan-out worker from the orchestrator.

## Decision

- Local principal gains `act` built from the harness payload when it exposes a parent (`parent_session_id`
  / `agent_id`), capped at the same depth as A2A; absent → depth 0, as today.
- `principal_rules` may name `claude:<agent_type>` at any depth; a rule may set `max_act_depth`.
- Journal and span carry `act_depth`; bundle unchanged.
- Payload fields are verified against the empirical hook contract per client version (as in ADR 0023); an
  unknown shape → depth 0 and `principal_shape_unverified` in the journal, never a deny by itself.

## Implementation note (2026-11-04)

Claude Code subagents do not nest and share the session with the main thread (verified in the hook payload:
`agent_type` + `agent_id` inside a subagent, nothing on the main thread), so the local chain is fixed:
`claude:<agent_type>` acts for `claude:main` — `act: ["claude:main"]`, depth 1; the main thread has depth 0.
`principal_rules` may carry `max_act_depth` (0..8, schema-bounded like the A2A chain); the PDP denies deeper
principals with `act_depth_exceeded` (journal enum and metrics mapping updated). The policy-pack builder takes
`--max-act-depth SUB=N` and refuses a cap for a principal without a rule. The journal's start event records
`act_depth`; the `claude_read` and `codex_bash` spans carry `adf.act_depth`. `agent_id` is never recorded.
`hooks/test-subagent-principal.sh` ran red first (1 failure, 3 errors). The `principal_shape_unverified` journal
hint from the decision text was not needed: the depth is derived from the one field ADR 0023 already verifies.

## Options considered

1. **One run per subagent** — breaks correlation; rejected.
2. **Deny subagent reads by default** — unusable; rejected.

## Consequences

Positive: per-depth least privilege and attribution. Negative: depends on harness payload fields that may change. Reversibility: cheap.

## Residual risks

The chain is asserted by the harness; no cryptographic hop verification locally.

## Rollback

Ignore `act` on local edges; schema field stays optional.
