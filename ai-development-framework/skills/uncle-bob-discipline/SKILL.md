---
name: uncle-bob-discipline
description: The disciplined-AI backbone — TDD, clean boundaries, metrics-over-line-by-line review, human oversight on architecture. Underlies every other skill.
---

# Uncle Bob Discipline

> **Archetype:** Builder (backbone) — TDD and clean boundaries under every archetype.

The professional standard: tested, clean, boundaried, measured, human-governed for taste.

## The disciplines
1. **TDD.** Red → green → refactor. No production code without a failing test first.
2. **Clean functions/classes.** Small, one thing, intention-revealing, few args, no side-effect surprises.
3. **Clean architecture.** Dependencies point inward (policy ← detail). Details are plugins.
4. **Metrics as the gate.** Review by coverage/complexity/mutation/dependency structure, not by
   scrolling the diff. Humans review *taste* (names, design), machines review *conformance*.
5. **Human oversight where it matters.** Architecture and irreversible calls need a human.

## Why metrics > line-by-line
Line-by-line review doesn't scale to agent-speed output and misses systemic issues (coupling,
weak assertions). A mutation score and a dependency graph catch what a tired reviewer won't.

## Steps
1. Start from a failing test.
2. Write minimal code to pass (Ponytail ladder).
3. Refactor under green; keep functions small and boundaries clean.
4. Gate on metrics (`skills/quality-gates`).
5. Route architecture to a human + ADR.

## Quality gates
- [ ] Test written first
- [ ] Complexity/size/coverage/mutation green
- [ ] Dependencies point inward; no cycles
- [ ] Architectural calls have human sign-off + ADR

## Integration
Foundation for quality-gates, clean-code-enforcement, test-review, measurement-driven-improvement.
Balanced by Ponytail (write less) and powered by Graphify (see structure) + RTK (cheap metrics).
