# Loop: meta (router)

Not an archetype — the dispatcher. When the task's phase is unclear, load this and let
`skills/archetype-orchestrator` classify it, then jump to that loop.

## Quick routing
| The task is really about… | Archetype | Loop |
|---|---|---|
| "will this even work?" / unknown | Prototyper | `loops/prototyper.md` |
| "make the working thing solid" | Builder | `loops/builder.md` |
| "this is bloated / too expensive" | Sweeper | `loops/sweeper.md` |
| "is it moving the metric?" | Grower | `loops/grower.md` |
| "is it safe / reliable at scale?" | Maintainer | `loops/maintainer.md` |

Default when genuinely ambiguous: **Prototyper** (cheapest to be wrong in) → escalate as
evidence arrives. A task can pass through several loops in sequence; that's the normal path.
