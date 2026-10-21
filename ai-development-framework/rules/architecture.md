# Architecture rules (global)

1. **Dependencies point inward.** Policy (domain) never imports detail (framework/db/UI).
   Details are plugins to policy (Clean Architecture).
2. **Boundaries where language changes.** Bounded contexts, kept few (see `skills/ddd-agent-skill`).
3. **One transaction, one aggregate.** Invariants live behind a single root.
4. **No cycles.** The dependency graph is acyclic; a cycle is a design bug → staff-architect.
5. **Reversible by default.** Prefer cheap-to-reverse decisions; costly/irreversible ones need
   a human + an ADR (`docs/architecture-decision-records/`).
6. **Delete before you add.** The best architectural change removes a component (Ponytail).
7. **Graph is the map.** Model and verify structure via `/graphify query`, not memory.
