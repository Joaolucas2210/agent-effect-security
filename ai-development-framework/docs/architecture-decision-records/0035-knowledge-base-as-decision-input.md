# ADR 0035: knowledge base as decision input

- **Status:** Accepted — human acceptance on 2026-11-04 (maintainer); previously Proposed. Already practised: `docs/knowledge/` records, coverage map and the verification pass of 2026-11-04.
- **Date:** 2026-11-04
- **Depends on:** ADR 0026.
- **Scope:** `docs/knowledge/` layout and the rule that ties ADRs, incidents and evals together. Documentation only.

## Problem

Papers and incidents informed decisions but lived in chat, in `ai-development-framework/docs/research/`
(internal experiment logs, Portuguese) or nowhere. ADRs do not cite threats; public positioning cannot show
which real attack ADF covers, which it leaves residual, and why.

## Decision

- `docs/knowledge/` holds three record kinds, English only, no pt-BR sibling (records, like ADRs):
  - `threats/README.md` — `THR-NN` abstract threat classes, one table;
  - `incidents/INC-NN-slug.md` — one file per real case: vector, trifecta legs, OWASP ASI, lesson, ADF status
    (`covered | residual | out_of_scope`), ADR that changes the status, eval id;
  - `papers/README.md` — `PAP-NN` one table, with why it matters for ADF;
  - `coverage.md` — the single table used in public material.
- Rules: an ADR that adds an effect or moves the boundary cites ≥ 1 `THR-`; an `INC-` marked `covered`
  must name a green eval; a status change is a PR that touches `coverage.md`.
- Entries marked ⚠ have an unverified CVE id or date and may not be cited publicly until verified.

## Options considered

1. **Keep using `docs/research/`** — wrong purpose and language; rejected.
2. **One big `THREATS.md`** — does not scale to per-incident eval links; rejected.
3. **External wiki** — not offline-verifiable with the repo revision; rejected.

## Consequences

Positive: traceability threat → ADR → eval → claim. Negative: `hooks/docs_check.py` parity rule does not apply
to records; if the checker is extended, records must stay exempt. Reversibility: cheap.

## Residual risks

Records go stale; the `coverage.md` date is the honesty marker.

## Rollback

Delete the folder.
