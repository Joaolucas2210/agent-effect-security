# ADR 0032: write effect admit path (WP6)

- **Status:** Proposed — **blocked** until a design partner demand is recorded in `docs/product/IMPLEMENTATION_PLAN.md#registered-demand`.
- **Date:** 2026-11-04
- **Depends on:** ADRs 0026, 0028 (deny-only first), 0029, 0030.
- **Scope:** a second effect class, `write`, admitted by the PDP and executed by a PEP in the ephemeral worktree.
- **Threats:** THR-02; OWASP ASI05.

## Problem

Agents edit CI, deploy and agent configuration. ADR 0028 denies the dangerous subset; everything else is
unseen. Partners asking for "prove what the agent changed" need an admitted, evidenced write.

## Decision (sketch, to be completed with the partner)

- PDP: `effect_classes == {"write"}` admitted only with an exact `allowed_scopes` entry and `max_output_bytes`
  ceiling; `effect_not_supported_in_h2_02` stays for everything else.
- PEP: write happens in the harness-owned worktree, atomic (`tmp` + `rename`), with `before_sha256` /
  `after_sha256` in the receipt and an `idempotency_key` = `intent_digest`; a second attempt with the same key is
  `write_replayed` deny. The host decides whether the worktree result is applied to the checkout; ADF never
  touches the live checkout.
- Edges: Claude `Edit`/`Write` as `gate_only` (ADR 0029) first; mediated write only via the MCP server.

## Options considered

1. **Ship now** — no demand, violates the implementation-plan rule. Rejected.
2. **Mediate writes through git patches only** — simpler receipt (patch digest); kept as an option for the partner conversation.

## Consequences

Large: new runtime, new receipts, new trial counters. Reversibility costly once partners depend on it.

## Residual risks

A `gate_only` write proves the decision, not the bytes written by the native tool, exactly like reads.

## Rollback

Not applicable until implemented.
