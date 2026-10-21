# Traces & the improvement loop

Closes the outer loop of Fase 4: **Eval → Evidence → Diagnose → Proposal**.
The eval harness (`docs/evals/`) says *whether* a run resolved; this directory is
where recurring failures turn into small, verifiable change proposals.

Based on the current pattern (OpenAI cookbook *Agent Improvement Loop* / *Macro
Evals*, LangChain, Braintrust 2026): a trace is the evidence, a recurring failure
mode becomes a case, and the macro step asks *which problems repeat and where* —
then you make one targeted change and re-run the eval to prove it.

## The loop

```
make eval-agent-flow-all     # 1. Eval    — run every fixture, record outcomes to results.csv
                             # 2. Evidence — runs/<case>.trajectory.md (reason/act/observe)
make eval-diagnose           # 3. Diagnose — group failures, flag recurring, emit proposal stubs
                             # 4. Proposal — a human fills proposals/<case>.md, then re-runs the eval

make learn                   # same loop for the OTHER signals: gate failures, routine
                             # failures, PonyTail must-cuts, recurring task failures
                             # (reads docs/observability/events.jsonl). Runs eval-diagnose too.
make learn-apply             # 5. Propose — PR with the filled proposals (DRY_RUN=1 default)
```

- **Diagnose proposes; a human decides the fix.** No skill/hook/prompt is edited
  automatically — verification-first (CLAUDE.md principle 5).
- A case failing in **≥2 distinct commits** is flagged `RECURRING` (`make learn` uses ≥2
  distinct UTC days, since events carry a timestamp, not a commit).
- Confidence is mechanical: recurring → `medium`, single → `low`, never `high` automatically.
- `gate=skipped-*` (runtime absent) is **no signal**, not a failure.

## proposals/

- `TEMPLATE.md` — the format for a proposal (also what the stub is generated from).
- `<case>.md` — one per failing case. Generated as a stub by `eval-diagnose` **only
  if absent**; an existing file (human-edited) is left untouched.

A proposal is done when its change ships **and** `make eval-agent-flow CASE=<case>`
goes from `resolved=no` to `resolved=yes` with no regression in the other cases.

## Operational hand-offs

`docs/observability/` complements eval trajectories: it records archetype hand-offs, mode
switches, runtime token/budget data, and task duration. `make eval-agent-flow` writes to both
surfaces, so a fixture outcome can be correlated with its operational path without duplicating
the eval evidence.

## Scope (deliberately small)

No headless runner, no generic loop controller, no failure-signature clustering
until case volume earns them (Ponytail / roadmap Fase 4). Two diagnose writers —
`eval-diagnose` (results.csv) and `learn` (events.jsonl) — share this directory and
the `TEMPLATE.md` sections, but never each other's stub logic. Real anonymized run
samples feeding the same proposals are the next honest slice.
