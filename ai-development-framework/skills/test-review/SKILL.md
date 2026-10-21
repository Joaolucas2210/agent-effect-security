---
name: test-review
description: Judge test quality by mutation score and edge-case discipline, not just coverage. Use for /test and in the review panel.
---

# Test Review

> **Archetype:** Builder — judge tests by mutation score, not just coverage.

Coverage says lines *ran*. Mutation says tests *catch breakage*. Gate on mutation.

## Steps
1. **Coverage** on changed lines vs. gate (necessary, not sufficient).
2. **Mutation** on changed logic — surviving mutants = weak assertions → block.
3. **Edge cases:** boundaries, empty, null, concurrency, failure paths present.
4. **Minimalism (Ponytail):** one runnable check per non-trivial branch; no fixture sprawl,
   no per-getter tests. YAGNI applies to tests.
5. **Determinism:** no `Date.now`/unseeded random/order dependence.

## Example
```
rtk mutmut run
→ survivor: `>` mutated to `>=` in pricing.py:42 still passes  ❌
FIX: add boundary assertion at the threshold
```

## Quality gates
- [ ] Changed-line coverage ≥ gate
- [ ] No surviving mutants on changed logic
- [ ] Failure/edge paths tested
- [ ] Deterministic

## Integration
qa-reviewer agent · quality-gates · Ponytail (test minimalism) · RTK.
