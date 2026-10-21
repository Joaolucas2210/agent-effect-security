---
description: Gate check → update graph → open PR.
---

# /ship

Ship: **$ARGUMENTS**

Preconditions (all must hold):
1. `/review` clean (no blockers from any reviewer).
2. Quality gates green: coverage, complexity, mutation, dependency structure.
3. `/graphify .` run so the graph reflects the change.
4. ADR written if an architectural decision was made.
5. `make observability-complete` recorded the outcome and generated its trajectory; include `make metrics` in the PR summary.

Then: create a branch (never commit to `main` directly), commit, open a PR with a summary
that links the ADR and shows the metrics table. Confirm with the human before pushing.

Uses: `hooks/`, `skills/quality-gates`.
