---
name: clean-code-enforcement
description: Enforce Clean Code (Uncle Bob) mechanically — naming, small functions, one-thing, low arg count — via metrics where possible. Use in review and /build.
---

# Clean Code Enforcement

> **Archetype:** Builder — clean names, small functions, one-thing, enforced at build time.

Prefer a linter/metric over a human opinion for every rule that can be measured.

## Rules → enforcement

| Rule | Enforce with |
|---|---|
| Functions small (≤ ~50 lines) | lizard / eslint max-lines-per-function |
| Do one thing (low complexity) | cyclomatic ≤ 10 |
| Few arguments (≤ 3) | linter max-params |
| Intention-revealing names | reviewer judgment (not mechanizable) |
| No duplication (DRY) | jscpd / graph "duplicate structure" query |
| No dead code | coverage 0% + graph "no callers" |

## Steps
1. Run mechanical rules as gates (via RTK).
2. For DRY, ask the graph for duplicate structures before eyeballing.
3. Reserve human review for naming/intent — the part metrics can't see.
4. Apply the Boy Scout Rule **only** to code the task touches (Ponytail bound).

## Quality gates
- [ ] Size/complexity/args gates green
- [ ] No duplication flagged by graph/jscpd
- [ ] No dead code (0 callers + 0 coverage)
- [ ] Names reviewed by a human

## Integration
uncle-bob-discipline · quality-gates · Graphify (dupes/dead code) · Ponytail (bounded cleanup).
