---
name: measurement-driven-improvement
description: Trend quality metrics over time and target the worst offenders. Improvement is measured, not asserted. Use periodically and before refactors.
---

# Measurement-Driven Improvement

> **Archetype:** Grower — trend metrics, target the worst offender, prove the gain.

You can't improve what you don't measure. Track the gate metrics as time series; refactor
where the number is worst, prove the delta.

## Steps
1. **Snapshot** metrics each ship: `make metrics-snapshot` appends one row per commit
   (idempotent) to `docs/metrics/history.csv`. Stack gates it can't compute stay `na` —
   honest, not zero. Capture token savings with `make rtk-report`.
2. **Rank hotspots** — highest complexity × churn (from graph history) = refactor first.
3. **Target one.** Refactor the single worst offender; re-measure; keep the delta or revert.
4. **Token metrics too.** Track `rtk gain` and graph-hit rate — context efficiency is a metric.

## Graph-hit rate
Before reading large files, query the graph. Record the choice so the rate is real, not asserted:
```
echo hit  >> ai-development-framework/docs/metrics/graph-hits.log   # queried the graph first
echo miss >> ai-development-framework/docs/metrics/graph-hits.log   # opened big files without querying
```
Then `make graph-hit-rate` reports hits/total. No log yet ⇒ it says so, not a fake 100%.

## Example
```
/graphify query "top 10 files by complexity*churn"
→ billing/engine.py CCN 24, churn high → refactor target
after: CCN 9, mutation 78%  ✅ keep
```

## Quality gates
- [ ] Metrics snapshotted per ship
- [ ] Hotspot chosen by data (complexity × churn), not vibes
- [ ] Delta proven before/after
- [ ] Token efficiency trended (rtk gain, graph-hit rate)

## Integration
quality-gates · Graphify (churn/complexity) · RTK (gain) · uncle-bob-discipline.
