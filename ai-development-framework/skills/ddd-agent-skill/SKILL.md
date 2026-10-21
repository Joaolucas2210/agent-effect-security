---
name: ddd-agent-skill
description: Apply Domain-Driven Design pragmatically — ubiquitous language, bounded contexts, aggregates — without over-modeling. Use for /spec, /plan, and boundary decisions.
---

# DDD Agent Skill

> **Archetype:** Prototyper → Builder — sketch boundaries early, model them only when they hold.

DDD for taste and boundaries, Ponytail for restraint. Model the domain, not your imagination.

## Core moves
1. **Ubiquitous language.** Names in code == names the domain experts use. Store the glossary
   in the graph and reuse it.
2. **Bounded contexts.** Draw boundaries where the language changes meaning. Keep them few.
3. **Aggregates.** Cluster invariants behind one root. One transaction = one aggregate.
4. **Anti-corruption layer** only at real integration seams — not speculatively (YAGNI).

## Restraint rules (Ponytail ∩ DDD)
- No aggregate for a CRUD row with no invariants — it's a table.
- No repository interface with one implementation until a second appears.
- No event sourcing/CQRS unless the domain demands it; escalate the call to staff-architect + ADR.

## Steps
1. Extract the language from the PRD; align with the graph glossary.
2. Identify invariants → aggregates. Everything else stays simple.
3. Mark context boundaries; only add ACLs where languages actually clash.
4. Big tactical patterns (ES/CQRS/sagas) → ADR + human sign-off.

## Quality gates
- [ ] Code names match domain language (graph glossary)
- [ ] Aggregates justified by invariants, not habit
- [ ] No speculative tactical patterns
- [ ] Context boundaries recorded in an ADR

## Integration
staff-architect · Ponytail · Graphify (glossary + context map) · uncle-bob-discipline.
