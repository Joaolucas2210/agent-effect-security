# Quality thresholds (tune per repo)

The numbers the gates enforce. Change them here; hooks and `skills/quality-gates` read from here.
`hooks/shell-complexity.sh` parses the Default column of this table at runtime — the table is
the single source of truth, not a copy of what the scripts hardcode.

| Gate | Metric | Default | Rationale |
|---|---|---|---|
| Coverage | changed-line % | ≥ 80% | necessary floor, not the real gate |
| Mutation | killed / total | ≥ 70% | the real gate — tests must catch breakage |
| Complexity | cyclomatic / fn | ≤ 10 | one-thing functions (all languages, shell included) |
| Shell body | cyclomatic / script top-level | ≤ 20 | ratcheting — see below |
| Size | fn length | ≤ 50 lines | readability |
| Args | params / fn | ≤ 3 | low coupling |
| Dependency | import cycles | 0 | acyclic architecture |
| Evals | changed skill/command/hook with an eval or a waiver | 100% | Evaluation-Driven Development |

## Notes
- Mutation > coverage. A 95%-covered file with surviving mutants still fails.
- Raise thresholds gradually via `skills/measurement-driven-improvement`; never lower to pass.
- Security gates are pass/fail and **not** tunable down (see `skills/security-review`).

## Shell complexity (why two numbers)
`lizard`/`radon` don't parse bash, so shell — this framework's own language — used to escape the
complexity gate entirely. `hooks/shell-complexity.sh` closes that hole:
`CCN = 1 + (if|elif|while|until|for) + && + || + case branches`.

- **Functions** are reusable units and are held to the same **≤ 10** as every other language.
- A **script top-level body** is a linear entry point where each `cmd || fail` guard counts as a
  branch, so it gets its own declared number (**≤ 20**) instead of a pass. It is a **ratchet**:
  the target is 10, reached by extracting bodies into functions (`main "$@"`). Lower this number
  as that happens — never raise it to make a red gate green.
- The function length gate (≤ 50) applies to functions only; a long linear script is not a
  50-line function violation, and pretending otherwise would be a fake failure.

## Evals (Evaluation-Driven Development)
A changed `skills/`, `commands/` or `hooks/` file must be covered by an eval case
(`docs/evals/fixtures/*/task.md` declaring `covers: <path>`), by a `hooks/test-*.sh` self-test that
exercises it, or by an explicit dated waiver in `docs/evals/waivers.md`. Enforced by
`hooks/eval-required.sh`; run it with `make eval-required`.
