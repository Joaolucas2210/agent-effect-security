---
name: quality-gates
description: The objective merge gate — coverage, cyclomatic complexity, mutation score, dependency structure. Metrics block the ship, not opinions. Use for /test and /ship.
---

# Quality Gates

> **Archetype:** Builder + Maintainer — the objective floor that blocks the ship.

Uncle Bob's discipline made mechanical: **the number is the gate.**

## The gates (tune thresholds per repo in `rules/quality-thresholds.md`)

| Gate | Metric | Default threshold | Tool (example) |
|---|---|---|---|
| Coverage | changed-line % | ≥ 80% | pytest-cov / c8 / jacoco |
| Complexity | cyclomatic / fn | ≤ 10 | radon / lizard / eslint-complexity |
| Complexity (shell) | cyclomatic / fn, body ≤ 20 | ≤ 10 | `hooks/shell-complexity.sh` (no dep) |
| Evals | changed behaviour evaluated | 100% | `hooks/eval-required.sh` + `hooks/eval-agent-flow.sh` |
| Mutation | killed / total | ≥ 70% | mutmut / stryker / pitest |
| Dependency | cycles, fan-in/out | 0 cycles | pydeps / madge / dependency-cruiser |
| Size | fn length | ≤ 50 lines | lizard |
| **PonyTail Review** | over-engineering | 0 must-cut findings | `skills/ponytail` (final pass) |

## Steps
0. `make quality` runs the wall; `make complexity` and `make eval` run the shell and eval halves alone.
1. Run each gate via RTK (`rtk <tool>`), capture the number, not the wall of output.
2. Compare to threshold. Any miss = **block**. A gate that could not run is **skipped, never green** —
   in CI, zero gates evaluated is a hard failure.
3. Mutation survivors → strengthen tests (don't pad line coverage).
3b. New skill / command / hook / routine? It needs an eval case, a `hooks/test-*.sh`, or a dated
   waiver in `docs/evals/waivers.md` — `make eval-required` is the gate (Evaluation-Driven Development).
4. Dependency cycles → route to `staff-architect` (boundary problem).
5. **PonyTail Review Gate** (final, after the numbers are green) — one lightweight pass:
   *"What here could be deleted, inlined, or replaced by stdlib/native without losing behavior?"*
   Any must-cut finding blocks the ship until cut or justified with a `// ponytail:` note.
6. Record completion with `make observability-complete` and inspect `make metrics`; missing token/cost values stay `na`, never guessed.
7. Update the graph so metrics reflect the shipped state.

## Example
```
rtk pytest --cov            # coverage: 84% ✅
rtk lizard src/             # max CCN 7 ✅  fn length 41 ✅
make complexity             # shell: max fn CCN 10, body 18 ✅
rtk mutmut run              # killed 73% ✅
rtk pydeps --show-cycles    # 0 cycles ✅
make eval                   # cases resolved ✅  changed behaviour evaluated ✅ → SHIP
```

## Quality gates (meta)
- [ ] Every gate has a number, checked against threshold
- [ ] No line-by-line review substituted for a failing metric
- [ ] Survivors/cycles escalated, not ignored
- [ ] PonyTail Review Gate run last: nothing left to delete/inline (or justified)
- [ ] Every skipped gate is named in the output — no silent pass
- [ ] Changed behaviour is evaluated or waived with a reason and a date

## Integration
RTK (compressed metric output) · Graphify (dependency structure) · uncle-bob-discipline ·
measurement-driven-improvement (trend the numbers).
