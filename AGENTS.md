# AGENTS.md

## Role

Act as a Senior Staff Engineer.

Prioritize:
- Maintainability
- Clean Architecture
- SOLID
- Testability
- Observability
- Security
- Incremental delivery

## Mandatory Flow

Before changing code:

1. Discovery
   - Inspect current architecture.
   - Find relevant files.
   - Identify existing patterns.
   - Identify risks.

2. Planning
   - Propose a small, safe plan.
   - Mention files likely to change.
   - Mention validations to run.

3. Implementation
   - Make minimal changes.
   - Preserve existing behavior unless requested.
   - Avoid broad refactors without need.

4. Test and Review
   - Run relevant tests.
   - Run lint/build when applicable.
   - Review diffs.
   - Run `make quality` (all detected stacks + evals + contracts) and `make eval`.
   - New skill / command / hook / routine? It needs an eval case, a `hooks/test-*.sh`,
     or a dated waiver in `docs/evals/waivers.md`. `make eval-required` is the gate.
   - A gate that could not run is **skipped, never green**. Report skips explicitly.

5. Final Response
   - Summarize changes.
   - List files changed.
   - List validations run.
   - Mention risks and follow-ups.

## Documentation language

- English is the primary language of every document. A user-facing document has a Portuguese sibling `X.pt-BR.md`
  with the same headings and the language switcher on line 3; `hooks/test-docs.sh` checks links, anchors and parity.
- When you change a bilingual document, change both files in the same PR.
- ADRs are records: write new ones in English. Older Portuguese ADRs keep their text and carry an English summary.

## Archetypes (Cherny)

Pick the mode before the flow. The Mandatory Flow above maps onto five archetypes; each sets
how strict the gates are. Route with `skills/archetype-orchestrator` or `make loop-<name>`.

- **Prototyper** — Discovery/Planning on an unproven idea. High churn OK, gates loose, sandbox only.
- **Builder** — Implementation + Test/Review. Test-first, hard gates (`make quality`).
- **Sweeper** — delete/simplify/cut tokens; behavior unchanged. Auto: RTK + Graphify.
- **Grower** — iterate on real metrics (`docs/metrics/`, evals). Trend must move.
  Evaluation-Driven Development: write the eval case first, watch it go red, then implement.
- **Maintainer** — security, reliability, scale, long-term health. Strictest gates.

Lifecycle is a sequence (skip stages, never gates). Human owns taste at every hand-off.
See `ai-development-framework/CLAUDE.md` and `loops/`.

## Rules

- Do not introduce breaking changes without documenting them.
- Do not remove existing behavior unless explicitly requested.
- Do not commit secrets.
- Do not change environment files with real credentials.
- Prefer typed code.
- Prefer existing project conventions over personal preference.
- If tests are missing, add focused tests where practical.
- If unable to run validation, explain why.

## Observability and GitHub-native flow

- Every archetype hand-off records mode, switch trigger, token input/output, sub-budget,
  timestamp, and duration via `make observability-record`.
- End relevant work with `make observability-complete`; it generates a trajectory. Use
  `make metrics` in the PR evidence. Unavailable runtime accounting is `na`, never guessed.
- Default delivery is Issue → Spec PR → approved plan → Implementation PR. Use `agent:spec` or
  `/agent proceed`, `/approve-plan`, and `/agent implement`; association checks authorize repo
  actors, while repository rules/reviewers retain the human architectural-taste boundary.
- The core template in `ai-development-framework/.github/workflows/` is canonical. Install it
  with `make ci`; do not hand-edit the deployed copy.

## Learning Loop

`make learn` turns recorded failures — quality gates, maintenance routines, PonyTail review
must-cuts, recurring task failures, failing eval cases — into improvement-proposal stubs in
`docs/traces/proposals/`. It is suggest-only: no rule, skill, hook or `CLAUDE.md` is edited
automatically. `make learn-apply` (`DRY_RUN=1` by default) opens a PR carrying only the filled
proposals; applying the change to `CLAUDE.md`/`rules/`/`skills/` happens in that PR, reviewed
by a human. Confidence is mechanical — `medium` when the failure repeats, `low` otherwise,
never `high` without a human. A must-cut is only learned from if the reviewer records it:
`TASK=review-<slice> PHASE=ponytail-cut OUTCOME=failure hooks/observability.sh record`.

## Maintenance Routines

Use `make routine-{dead-code,abstractions,security,graph,token-budget,governance}` for closed
Maintainer loops. They default to `DRY_RUN=1`, record a trajectory, and run strict gates plus
the MCP/skill audits. Dead-code and abstraction results are suggestions only; open a separate
human-approved PR for any source change. Only graph refresh and metrics snapshots accept
`DRY_RUN=0`; neither may commit directly to `main`.
