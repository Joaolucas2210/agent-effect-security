# Eval waivers

`hooks/eval-required.sh` fails when a changed `skills/`, `commands/` or `hooks/` file has no
eval case and no self-test. A waiver is the escape hatch, and it is **deliberately noisy**:
one line, a reason, a date. Reviewers read this file; a growing list is a finding, not a habit.

Format (the gate parses it literally):

```
- `path/to/file` — reason (YYYY-MM-DD)
```

## Active waivers

- `ai-development-framework/commands/eval.md` — prompt surface for `make eval`; the gate it documents is covered by `hooks/test-eval-required.sh` and `hooks/test-shell-complexity.sh` (2026-08-21)
- `ai-development-framework/commands/learn.md` — prompt surface for `make learn`; the loop it documents is covered by `hooks/test-learn.sh` (2026-08-24)
- `ai-development-framework/hooks/thresholds.sh` — 8-line sourced reader with no branches; exercised by every gate self-test that reads a threshold (2026-08-21)
- `ai-development-framework/hooks/learn-apply.sh` — opens a PR via `gh`; evaluating it would require a live remote, and a dry-run eval would assert nothing real (2026-08-21)
- `ai-development-framework/hooks/rtk-wrap.sh` — 9-line passthrough wrapper around an optional external binary (2026-08-21)
- `ai-development-framework/hooks/graph-update.sh` — 11-line wrapper; the graph gate itself is `hooks/graph-check.sh`, which has a self-test (2026-08-21)
