# Loop: Grower (growth)

**Goal:** iterate on what real usage and metrics say — not on taste or guesses.

## Mindset
No change without a metric that says it's needed and a metric that confirms it worked.
Target the worst offender first. Small, measured increments beat big rewrites.

## Active
- `skills/measurement-driven-improvement` — trend metrics over time, pick the worst
- `skills/quality-gates` — the objective floor while iterating
- Evals: `make eval-agent-flow-all` → `make eval-diagnose` (recurring-failure proposals)

## Signal sources
- `docs/metrics/history.csv` (coverage/mutation/complexity/cycles/graph/rtk per ship)
- `docs/evals/results.csv` · `make graph-hit-rate` · `make token-budget`

## Gates
Every iteration appends a row (`make metrics-snapshot`). Trend must move the right way or
the change is reverted. Improvement is measured, never asserted.

## Exit → Maintainer
When growth stabilizes: fold the wins into durable rules/ADRs and hand to Maintainer.
