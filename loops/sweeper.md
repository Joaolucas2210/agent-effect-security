# Loop: Sweeper (optimization)

**Goal:** remove bloat and cost. Deletion over addition. Fewer tokens, fewer lines, same behavior.

## Auto-activated tooling
- **RTK** — every command through `rtk <cmd>`; never paste raw output. Report `rtk gain`.
- **Graphify** — query the graph to find duplication / dead nodes instead of grepping files.

## Active
- `skills/ponytail` (level `ultra` for aggressive sweeps) · `skills/rtk-integration`
- `skills/graphify` · `skills/measurement-driven-improvement` (prove the reduction)

## What to cut
Reinvented stdlib · one-impl interfaces · factories for one product · config for a constant ·
speculative flexibility · dead flags · files the graph shows nothing depends on.

## Gates
Behavior unchanged: the existing test + `make quality` still green **after** the cut.
A sweep that changes behavior is a Builder task, not a Sweeper task.

## Exit
Report the delta: lines removed, `rtk gain` %, graph nodes dropped. Never simplify away
validation, error handling, security, or accessibility (`rules/minimalism.md`).
