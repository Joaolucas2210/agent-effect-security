# Loop: Builder (implementation)

**Goal:** turn a proven prototype into production-grade code. Correctness is the product.

## Mindset
Least code that works — but now with tests, boundaries, and error handling at trust
edges. Ponytail still governs *how much* you write; it never waives a real control.

## Active
- `skills/implementation` · `skills/build`
- `skills/clean-code-enforcement` · `skills/uncle-bob-discipline` (TDD, small, one-thing)
- `skills/test` · `skills/quality-gates` · `skills/rtk-integration`
- `skills/graphify` — locate the exact insertion point

## Gates (hard)
Coverage + cyclomatic complexity + mutation + dependency cycles must be green
(`make quality`). Test-first for non-trivial logic. Shortcuts carry a `// ponytail:` upgrade path.

## Exit → Sweeper / Maintainer
Feature works and gates pass. Hand to Sweeper to simplify, or Maintainer to harden for scale.
