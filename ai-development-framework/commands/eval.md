---
description: Run the evals — cases, eval coverage of the diff, and diagnosis of what keeps failing.
---

# /eval

Evaluation-Driven Development: **$ARGUMENTS**

```bash
make eval                      # every case + EDD coverage of the diff + diagnosis
make eval-agent-flow CASE=x    # one case
make eval-required             # only the gate: is this change evaluated?
```

Steps:
1. Run the cases. `resolved` comes from the fixture's own gate — never from an opinion about
   the diff. A missing trajectory is a hard fail: the evidence of a run is part of the run.
2. Read the EDD gate. A new skill, command, hook or routine needs an eval case
   (`docs/evals/fixtures/<case>/task.md` with `covers: <path>`), a `hooks/test-*.sh`, or a
   dated waiver in `docs/evals/waivers.md`. Waivers are read by reviewers — justify, don't dodge.
3. New behaviour without a case? Write the case **first**, watch it go red, then implement.
   `cp -r docs/evals/fixtures/sum-bug docs/evals/fixtures/<case>` is the whole setup.
4. Feed the loop: failures land in `docs/evals/results.csv` and `docs/observability/events.jsonl`;
   `make learn` turns the recurring ones into improvement proposals. Never edit the CSV by hand.

Uses: `skills/quality-gates`, `hooks/eval-agent-flow.sh`, `hooks/eval-required.sh`, `hooks/eval-diagnose.sh`.
When NOT to use: a docs-only change with no behaviour — say so in the PR instead of waiving.
