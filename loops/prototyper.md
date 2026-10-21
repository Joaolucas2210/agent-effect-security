# Loop: Prototyper (exploration)

**Goal:** learn whether an idea is worth building. Throwaway code is a feature, not debt.

## Mindset
Optimize for speed of learning, not correctness. Highest acceptable churn. One path,
happy case only. Name the unknown you're resolving before writing anything.

## Active
- `skills/planning` · `skills/ddd-agent-skill` (sketch boundaries, don't model them)
- `skills/graphify` — query to locate, never re-read whole files
- `skills/ponytail` — one line beats fifty; question if the idea needs code at all

## Gates (loose)
- No coverage/mutation gate. One runnable check only if the logic is non-trivial.
- Work in `sandbox/`. Nothing here ships without passing through Builder first.

## Exit → Builder
When the idea proves out: the unknown is resolved and someone (human) says "make it real."
Everything not carried into Builder gets deleted, not archived.
