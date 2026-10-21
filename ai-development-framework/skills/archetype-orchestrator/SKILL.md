---
name: archetype-orchestrator
description: Classify a task into one of Cherny's five archetypes (Prototyper/Builder/Sweeper/Grower/Maintainer) and route it to the right loop, skills, and gates. Use at the start of a task when the phase is unclear.
---

# Archetype Orchestrator

The dispatcher for archetype-guided work. It answers one question — *what mode is this?* —
then hands off. It does not do the work itself; it routes to `loops/` and the skills below.

## Classify (first match wins)
1. Unknown whether the idea works, or "will this fly?" → **Prototyper**
2. A proven prototype must become production code → **Builder**
3. Code is bloated, duplicated, or too token-expensive → **Sweeper**
4. Question is "is it moving the metric / PMF?" → **Grower**
5. Question is safety, reliability, or health at scale → **Maintainer**

Genuinely ambiguous → default **Prototyper** (cheapest to be wrong in), escalate as evidence arrives.

## Route

| Archetype | Loop | Skills it activates | Gate posture |
|---|---|---|---|
| Prototyper | `loops/prototyper.md` | `skills/planning`, `skills/ddd-agent-skill` | loose (1 check) |
| Builder | `loops/builder.md` | `skills/implementation`, `skills/uncle-bob-discipline`, `skills/quality-gates` | hard |
| Sweeper | `loops/sweeper.md` | `skills/ponytail`, `skills/rtk-integration` | behavior-unchanged |
| Grower | `loops/grower.md` | `skills/measurement-driven-improvement` | trend-must-move |
| Maintainer | `loops/maintainer.md` | `skills/security-review`, `skills/quality-gates` | strictest |

`skills/graphify` is cross-cutting — every archetype queries the graph before deep reads.

## Cross-archetype defaults
- **RTK + Graphify** auto-activate in **Sweeper** (aggressive token/dedup pass).
- The normal lifecycle is a **sequence**: Prototyper → Builder → Sweeper → Grower → Maintainer.
  A task may skip stages, never gates. Reviewer agents run in Builder and Maintainer.
- Human owns taste/irreversible calls at every hand-off (`agents/staff-architect.md`).

## Dynamic switching (mid-task handoff)
Re-classify when a signal fires mid-task — don't finish in the wrong mode. One switch at a time.

| Signal mid-task | Switch to | Handoff (one line) |
|---|---|---|
| prototype proved out, "make it real" | Builder | freeze the sketch; carry only what's used, delete the rest |
| working code feels bloated / too costly | Sweeper | snapshot gates green first; the sweep must keep them green |
| gates green but a metric is the question | Grower | baseline the metric before touching anything |
| a security / scale risk surfaces | Maintainer | stop feature work; risk gate before continuing |
| Builder+ finds the idea was wrong | Prototyper | back to sandbox; the production attempt is the throwaway |

Handoff = **carry** (decision + graph delta) · **reset** (gate posture + token sub-budget) · **name** the trigger. Log the switch; never drift silently. Before the hand-off, run `make observability-record` with `TASK`, `ARCHETYPE`, `PHASE`, `TOKENS_IN`, `TOKENS_OUT`, `BUDGET_REMAINING`, `DURATION_SECONDS`, and, when applicable, `SWITCHED=true TRIGGER=<signal>`. At task exit, run `make observability-complete` with the same structured fields and `OUTCOME=success|failure`; it writes the trajectory automatically.

## Token budget (hierarchical)
Parent budget = the task total (`make token-budget`). Each archetype draws a sub-budget; a switch resets it. Crossing the ceiling is a **termination condition**, not a suggestion. RTK + Graphify are the levers.

| Archetype | Budget posture | Terminate when |
|---|---|---|
| Prototyper | tightest — sandbox, one path | learning cost > building cost → promote or drop |
| Builder | moderate — tests earn tokens | feature done + gates green |
| Sweeper | negative — must *return* tokens (report `rtk gain`) | the delta stops paying |
| Grower | metered per iteration | trend flat 2 rounds |
| Maintainer | audit-scoped | audits pass, steady state |

## Output format
```
ARCHETYPE: <one of five>  (because <the deciding signal>)
LOOP: loops/<file>.md
ACTIVATE: <skills>
GATES: <posture>
NEXT: <likely next archetype>
```

## When NOT to use
Skip this when the archetype is already obvious or the user named a command
(`/build` = Builder, `/review` = Maintainer). Don't classify a one-line edit — just do it.
Not a state machine: it routes once; re-run it only when the task's phase actually changes.

## Integration
`loops/` (mode context) · every skill in `skills/` (the work) · `agents/staff-architect.md` (taste).
