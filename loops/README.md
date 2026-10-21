# loops/ — archetype operating modes

Each file is a **minimal CLAUDE.md** for one of Cherny's five archetypes plus a `meta`
router. Loading one puts the agent in that mode: which skills activate, how strict the
gates are, when to exit. This is context, not code — the whole point is to load *less*.

| File | Archetype | Phase alias | One-line intent |
|---|---|---|---|
| `prototyper.md` | Prototyper | exploration | Explore fast, high churn OK, gates loose |
| `builder.md` | Builder | implementation | Prototype → production, test-first, gates hard |
| `sweeper.md` | Sweeper | optimization | Delete, simplify, compress tokens (RTK + Graphify auto) |
| `grower.md` | Grower | growth | Iterate on real metrics / PMF |
| `maintainer.md` | Maintainer | maintenance | Security, reliability, long-term health at scale |
| `meta.md` | (router) | meta | Pick the archetype for the task → `archetype-orchestrator` |

Enter a mode: `make loop-sweeper` (or the phase alias, `make loop-optimization`).

**Flat on purpose (ponytail).** No per-archetype subfolders until a loop actually
produces artifacts to store. When one does, give *that* archetype a folder — not all six.
