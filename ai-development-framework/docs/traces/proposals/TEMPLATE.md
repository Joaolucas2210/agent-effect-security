# Improvement proposal — <case>

> One recorded failure → one small, verifiable change. `eval-diagnose` (eval cases) and
> `make learn` (gates, routines, review cuts, recurring tasks) generate this stub from the
> Evidence; a human fills the rest. Both writers emit the same sections.

## Evidence
- Failing runs: **<n>** across **<n>** commit(s) [RECURRING if ≥2]
- Last failure: `<date> <commit>`
- Trajectory: `docs/evals/runs/<case>.trajectory.md`
- Gate/results: `docs/evals/results.csv` (rows where case=<case>, resolved=no|gate=fail)

## Hypothesis (human)
_Why does the agent flow fail this case? Which step — reason, act, or gate reading?_

## Proposed change (human)
_Target ONE of: a skill, a hook, or a prompt. Smallest change that could fix it._
- [ ] skill: `…`
- [ ] hook: `…`
- [ ] prompt/command: `…`

## Expected impact
_Which metric moves, and by how much? (gate pass, complexity, mutation, coverage, tokens)_

## Confidence
**low | medium** — mechanical: recurring evidence => medium, single occurrence => low.
Only a human raises this to **high**, in the PR that applies the change.

## Validation
- [ ] `make eval-agent-flow CASE=<case>` → resolved=yes after the change
- [ ] no regression in other cases (`make eval-agent-flow-all`)
