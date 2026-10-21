---
case: <case-name>
model: <model-id>
iterations: <n>        # how many reason/act/observe loops the run took
est_tokens: <n>        # rough token cost of the run
resolved: <yes|no>     # final outcome (mirrors results.csv; the gate is the source of truth)
gate: <pass|fail>
---

# Trajectory — <case-name>

Reason → Act → Observe → Decide, one block per iteration. This is the evidence
of a run; the harness treats a missing trajectory as a hard fail.

## Iteration 1
- **Reason:** why this step, given `task.md` and the gate assertions.
- **Act:** the concrete command/edit.
- **Observe:** what the gate reported (`resolved`, `gate`, which assertions).
- **Decide:** continue (with next step) or stop.
