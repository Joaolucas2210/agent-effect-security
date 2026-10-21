# Agent-flow evals

Minimal harness to run the agent flow against a fixed task and **measure whether
it resolved** — the outer loop the inner build/gate loop can't see. Roadmap Fase 4.
Polyglot by design: the gate is a stdlib test runner, picked per fixture language.

**Evaluation-Driven Development in one line:** new behaviour gets its eval *before* the
implementation, and a change that evaluates nothing does not merge (`make eval-required`).

## What a case is

```
fixtures/<case>/
  task.md            # the spec handed to the agent (goal + objective done criteria)
                     # optional: `covers: <path>` lines — what this case evaluates (EDD gate)
  solution.{js,py}   # what the agent edits
  test.js            # JS gate  — node --test (stdlib)
  test_*.py          # Python gate — python3 -m unittest discover (stdlib)
runs/<case>.trajectory.md   # reason/act/observe of a run (see runs/TEMPLATE.trajectory.md)
results.csv                 # one row per run: date,commit,case,resolved,iterations,est_tokens,gate
```

A fixture is **one language**: it has a `test.js` **or** `test_*.py`, and the harness
runs the matching stdlib runner. No new dependency — `node:test` and `unittest` ship
with the runtime. (The `unittest.TestCase` files also run under pytest unchanged, if
you install it.)

## Run it

```bash
make eval                            # everything: all cases + EDD gate + diagnosis
make eval-check                      # same eval gates, without writing evidence
make quality-check                   # quality gates, without writing eval evidence
make eval-agent-flow                 # one case, default CASE=sum-bug (JS)
make eval-agent-flow CASE=median-bug # Python
make eval-required                   # only the gate: is this change evaluated? (BASE=<ref>)
```

In the agent, `/eval` drives the same three steps and tells you when to write a case first.

- `resolved = fixture gate passed`. **Exit code = resolved** → it behaves like a gate.
- **Trajectory is mandatory** — no `runs/<case>.trajectory.md` ⇒ hard fail. Capturing
  what the agent thought/did/observed is first-class, not optional.
- Required runtime absent (`node`/`python3`) ⇒ honest skip (`resolved=na`, exit 0),
  never a fake pass.
- Result is appended to `results.csv`, idempotent per `commit+case`, and the same outcome is
  recorded as a `Grower` event in `docs/observability/events.jsonl` with an automatic trajectory.
- `make eval-check` and `make quality-check` set `ADF_EVAL_WRITE=0`: they run the gates but
  do not write results, events, trajectories, or proposals. With `ADF_EVENTS_V1=1`, check mode
  fails closed with `eval_persistence_disabled` rather than creating an event stream.
- `ADF_EVAL_WRITE` is opt-in: an absent value or `1` preserves the existing write behavior.

## How it proves the concept (fail → pass)

The fixture starts RED (a seeded bug). Run the harness ⇒ `resolved=no` (gate catches it).
Fix `solution.*` + write the trajectory ⇒ `resolved=yes`. Both rows land in `results.csv`.
After that the case is a **regression guard** for the agent flow. `median-bug` proves the
same loop closes in a second language.

## The EDD gate (`hooks/eval-required.sh`)

A changed `skills/`, `commands/` or `hooks/` file must be covered by **one** of:

| Coverage | How | Use it for |
|---|---|---|
| eval case | `covers: <path>` in a fixture's `task.md` (trailing `/` = directory) | agent-flow behaviour |
| self-test | a `hooks/test-*.sh` that mentions the file (a `test-*.sh` covers itself) | hooks and gates |
| waiver | `- \`<path>\` — reason (YYYY-MM-DD)` in `waivers.md` | genuinely unevaluable surfaces |

Waivers are deliberately noisy: reviewers read `waivers.md`, and a growing list is a finding.
No base ref to diff against (shallow clone, no origin) = honest skip, reported as *not checked*.

## How the Learning Loop consumes this

```
make eval  ─┬─ results.csv          (one row per run: resolved / gate / iterations / est_tokens)
            └─ events.jsonl         (the same outcome as a Grower event + a trajectory)
                  │
make learn  ──────┴─ eval-diagnose.sh  → failing case, recurring across ≥2 commits
                     learn.sh          → failing gate/routine, recurring across ≥2 days
                          └─ docs/traces/proposals/<case>.md   (stub: evidence + human hypothesis)
                                └─ make learn-apply → PR (a human decides the fix)
```

`make metrics` prints the eval line (`cases / runs / resolved / resolve_rate`) next to the
token and outcome counters, so a regression is visible without opening the CSV.

## Adding a case

1. `cp -r fixtures/sum-bug fixtures/<case>` (or `median-bug` for Python).
2. Rewrite `task.md` with the goal + an objective done criterion.
3. Write the gate — `test.js` (JS) **or** `test_*.py` (Python) — small and objectively
   checkable. Seed the bug in `solution.*` so it ships RED.
4. Copy `runs/TEMPLATE.trajectory.md` to `runs/<case>.trajectory.md` and fill it in.
5. Declare what it evaluates: add `covers: <path>` lines to `task.md` (this is what satisfies
   the EDD gate for the skill/command/hook the case exercises).
6. `make eval-agent-flow CASE=<case>` → records the row. Write the case first and watch it go
   **red** before implementing: a case that has never failed has never proven anything.

Keep each case small. Don't build a generic loop controller or a headless runner until
the roadmap earns them (Ponytail). Running every case at once is the next honest slice.
