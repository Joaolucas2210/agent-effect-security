---
description: Run the multi-agent review panel (metrics-first) on the current diff.
---

# /review

Review the current diff (or **$ARGUMENTS**).

Orchestration:
1. Refresh the graph on the diff, then dispatch reviewers **in parallel**:
   - `backend-reviewer`, `database-reviewer` (if schema/queries touched),
     `qa-reviewer`, `security-reviewer`.
2. Each returns metrics + blockers, not line-by-line prose.
3. `staff-architect` adjudicates design escalations.
4. Aggregate: **any block = not shippable.** Report metrics table + cuts (Ponytail) + escalations.

Uses: `agents/*`, `skills/pr-review`, `skills/quality-gates`.
