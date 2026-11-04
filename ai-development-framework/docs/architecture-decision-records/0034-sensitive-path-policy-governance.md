# ADR 0034: sensitive-path policy governance

- **Status:** Proposed — awaits human acceptance.
- **Date:** 2026-11-04
- **Depends on:** ADR 0008 (Accepted), 0026, 0035.
- **Scope:** how `sensitive_path_policy_vN` and `agent_config_policy_vN` change. Process, not code.

## Problem

`sensitive_path_policy_v1` is a fixed list (`.env`, `.git`, `secrets`, `credentials`, `id_rsa`, `*.pem`,
`*.key`). Design partners will send their own lists (CONTROL_PLANE "what we ask in return"). Without a
process the list grows by hand, loses reproducibility, and tempts content-based rules.

## Decision

- A path rule enters only through: (1) a `THR-`/`INC-` record or a partner request with a redacted example,
  (2) a red eval case, (3) a new policy version file (`-v2.json`), never an edit in place, (4) one ADR line
  in this file's changelog table. Old versions stay loadable; the bundle already carries the policy version.
- Rules are path components or suffixes only. A proposal that needs content inspection is rejected by rule.
- Partner-specific additions live in the host-pinned policy pack, not in the runtime list.

| Version | Date | Added | Source |
| --- | --- | --- | --- |
| v1 | 2026-09 | baseline | ADR 0008 |

## Options considered

1. **Allow glob/DSL** — ADR 0011 forbids; rejected.
2. **Per-partner forks of the runtime list** — breaks the "same code decides" property; rejected.

## Consequences

Slower growth, reproducible denylist, every rule traceable to a threat. Reversibility: cheap.

## Residual risks

A path-only list never covers secrets at arbitrary paths; that is accepted and stated (ADR 0026).

## Rollback

Process only; nothing to roll back in code.
