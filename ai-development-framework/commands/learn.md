# /learn — close the improvement loop

Turn recorded failures into improvement proposals. **Suggest-only**: no rule, skill,
hook or `CLAUDE.md` is edited by this command. It proposes; a human decides in a PR
(prime directive 5).

## Flow

```
make learn          # 1. Diagnose — read the recorded signals, write proposal stubs
                    # 2. Fill     — a human writes Problem/Change/Impact in each stub
make learn-apply    # 3. Propose  — open a PR carrying only the proposals
                    # 4. Apply    — the PR (reviewed by a human) edits CLAUDE.md/rules/skills
```

## What it reads (never re-derives)

| Signal | Source | Writer |
|---|---|---|
| Quality-gate failures | `docs/observability/events.jsonl` (`task=gate-*`) | `ci-quality-gates.sh` |
| Maintenance-routine failures | same log (`task=routine-*`) | `maintenance-routine.sh` |
| PonyTail review must-cuts | same log (`task=review-*`, phase `ponytail-cut`) | the reviewer, see below |
| Recurring agent-flow failures | same log (any task, `outcome=failure`) | `observability.sh` |
| Failing eval cases | `docs/evals/results.csv` | `eval-diagnose.sh` (fed by `make eval`) |
| Unevaluated changes | the diff vs base | `eval-required.sh` (blocks in `make quality`) |

One writer per signal class — `make learn` runs `eval-diagnose` **and** `learn.sh` so
stub logic is never duplicated.

## Recording a PonyTail must-cut

The review gate is a judgement, not a script, so it has to record its own signal:

```bash
TASK=review-<slice> ARCHETYPE=Sweeper PHASE=ponytail-cut OUTCOME=failure \
  ai-development-framework/hooks/observability.sh record
```

No record, no signal — `make learn` reports what was recorded and nothing else.

## Evals are the outer loop

`make eval` refreshes `results.csv` **and** records each run in `events.jsonl`, so both writers
above see the same run. Read the current state with `make metrics` — the `evals:` line reports
`cases / runs / resolved / resolve_rate`. A case that regressed is a proposal waiting to be written,
not a number to be argued with.

## Confidence is mechanical

`medium` when the failure repeats (≥2 distinct UTC days, or ≥2 commits for evals),
`low` for a single occurrence. **Never `high` automatically** — only the human who
applies the change raises it, in the PR.

## Graphify-first

Before proposing a change to a rule or skill, query the graph for what already
covers it: `/graphify query "which rule covers <topic>" --budget 1500`. A proposal
that duplicates an existing rule is a must-cut, not an improvement.
