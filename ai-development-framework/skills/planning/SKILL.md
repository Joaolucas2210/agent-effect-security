---
name: planning
description: Turn ideas/PRDs into minimal, ordered, graph-informed implementation plans. Use for /spec and /plan — before writing any code.
---

# Planning

> **Archetype:** Prototyper — turn a rough idea into a minimal, ordered plan before code.

Plan the least work that ships value. The graph tells you what already exists; Ponytail tells
you what not to build.

## Steps
1. **Query the graph.** `/graphify query "features/modules related to <task>"`. Reuse first.
2. **Write/refresh the PRD** from `docs/PRD-template.md`. Non-goals list should be long.
3. **Slice vertically.** Fewest end-to-end slices that each deliver value. Cut speculative work.
4. **Per slice:** files touched · test-first · gate impact · rollback.
5. **Escalate design.** Any architectural fork → `agents/staff-architect.md` → ADR.

## Example
```
/spec  invoice export to CSV
/plan  invoice export to CSV
→ Slice 1: endpoint + one query + test (uses existing InvoiceRepo, per graph)
→ Slice 2: streaming for large sets  [NON-GOAL for v1 — mark, don't build]
```

## Quality gates
- [ ] Graph consulted; reuse noted
- [ ] Non-goals explicit
- [ ] Each slice is vertical + testable
- [ ] Architectural decisions routed to ADR

## Integration
Ponytail (cut scope) · Graphify (reuse) · staff-architect (ADRs).
