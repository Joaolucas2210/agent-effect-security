---
name: pr-review
description: Orchestrate the multi-agent review panel, metrics-first, on a diff. Use for /review.
---

# PR Review

> **Archetype:** Maintainer — metrics-first review panel guarding the merge.

Dispatch specialist reviewers in parallel; aggregate to a single ship/block verdict.

## Steps
1. **Refresh the graph** on the diff (blast radius, callers, data flow).
2. **Dispatch in parallel** (`agents/`):
   - backend-reviewer · database-reviewer (if DB touched) · qa-reviewer · security-reviewer.
3. Each returns **metrics + blockers**, not prose walls.
4. **staff-architect** adjudicates escalated design questions.
5. **Aggregate:** any single block ⇒ not shippable. Emit metrics table + Ponytail cuts + escalations.

## Example output
```
VERDICT: BLOCK
| reviewer   | verdict | key metric        |
| backend    | pass    | CCN 7, coupling ok|
| database   | block   | migration locks   |
| qa         | block   | 2 mutants survive |
| security   | pass    | no taint paths    |
CUTS: src/util/wrapper.ts:12 → delete, stdlib Array.flat covers it
ESCALATE: repo split? → staff-architect
```

## Quality gates
- [ ] Graph refreshed before review
- [ ] All relevant reviewers ran
- [ ] Verdict is metric-backed
- [ ] Any block halts the ship

## Integration
agents/* · Graphify · quality-gates · Ponytail (cuts) · RTK.
