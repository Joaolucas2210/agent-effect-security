# CLAUDE.md — AI Development Framework (root rules)

Persistent rules for every agent in this framework. These OVERRIDE default behavior.

## Prime directives (in order)

1. **Smart context first.** Before any deep analysis, query the knowledge graph
   (`/graphify query "..."`) instead of re-reading files. Read full files only when the
   graph is insufficient. See `skills/graphify/SKILL.md`.
2. **Minimalism (Ponytail).** Write the least code that works. Climb the ladder: does it
   need to exist? → stdlib → native feature → existing dep → one line → minimum code.
   Mark deliberate shortcuts with `// ponytail:` comments. See `skills/ponytail/SKILL.md`.
3. **Token efficiency (RTK).** Terminal commands run through `rtk <cmd>` so output is
   compressed. Don't dump raw logs into context. See `skills/rtk-integration/SKILL.md`.
4. **Review by metrics (Uncle Bob).** Coverage, cyclomatic complexity, mutation score,
   dependency structure — the gate is the number, not a line-by-line skim. See
   `skills/uncle-bob-discipline/SKILL.md` and `skills/quality-gates/SKILL.md`.
5. **Human in the loop for taste.** Architecture, product trade-offs, and edge cases go to
   a human. Agents propose; humans decide on design. See `agents/staff-architect.md`.

## Archetypes (Cherny)

Every task runs in one of five modes. At the start of a task, if the mode is unclear, route
it with `skills/archetype-orchestrator` (or `make loop` to list, `make loop-<name>` to enter).
The prime directives above hold in **all** modes; the archetype only changes gate strictness
and which skills lead.

| Archetype | Leads with | Gates | Loop |
|---|---|---|---|
| **Prototyper** | explore, high churn, learn | loose (1 check) | `loops/prototyper.md` |
| **Builder** | prototype → production | hard (`make quality`) | `loops/builder.md` |
| **Sweeper** | delete, simplify, cut tokens | behavior-unchanged | `loops/sweeper.md` |
| **Grower** | iterate on real metrics | trend must move | `loops/grower.md` |
| **Maintainer** | security, reliability, scale | strictest | `loops/maintainer.md` |

Normal lifecycle is a sequence (Prototyper → Builder → Sweeper → Grower → Maintainer); skip
stages, never gates. **Sweeper auto-activates RTK + Graphify.** Human owns taste at each hand-off.

## Memory / state

- The **knowledge graph is the memory**. Keep it fresh: hooks update it on commit; run
  `/graphify .` after large changes.
- The **observability log is the hand-off evidence**. Record every archetype hand-off with
  `make observability-record`; complete tasks with `make observability-complete` so a trajectory
  exists before `/ship`. Missing runtime token/cost accounting is `na`, never estimated.
- ADRs in `docs/architecture-decision-records/` are the durable record of *why*.
- CLAUDE.md files (root + per-skill) are the durable record of *how*.

## Uncle Bob principles (condensed)

- **Tests are non-negotiable.** Red-green-refactor. A change without a test is unfinished.
- **Boundaries.** Dependencies point inward (toward policy, away from detail).
- **Small.** Functions do one thing. Files stay small. Names reveal intent.
- **Metrics over vibes.** Enforce complexity/coverage/mutation as gates, not opinions.
- **The Boy Scout Rule.** Leave it cleaner — but only touch what the task needs (Ponytail).

## Anti-patterns (reject on sight)

- Interface with one implementation. Factory for one product. Config for a constant.
- Speculative flexibility ("we might need..."). YAGNI.
- Re-reading whole files the graph already indexed.
- Dumping raw command output instead of RTK-compressed output.
- New dependency for what a few lines of stdlib solve.

## When NOT to be minimal

Never simplify away: input validation at trust boundaries, error handling that prevents
data loss, security controls, accessibility basics, or anything explicitly requested.

## Definition of Done

- [ ] Graph consulted before deep work
- [ ] Least-code solution (Ponytail); shortcuts commented
- [ ] Tests pass; coverage + complexity + mutation gates green
- [ ] Reviewer agents run (metrics report, not line-by-line)
- [ ] Graph updated (`/graphify .`/hook)
- [ ] Observability completion + trajectory recorded; `make metrics` included in the PR
- [ ] ADR written if an architectural decision was made
