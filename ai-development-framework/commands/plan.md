---
description: Break a PRD/task into a minimal, ordered implementation plan.
---

# /plan

Plan the implementation for: **$ARGUMENTS**

Steps:
1. Query the graph for affected modules, callers, blast radius — do not re-read whole files.
2. Break into the **fewest** vertical slices that ship value. Cut anything speculative (YAGNI).
3. For each slice: files touched, test to write first, gate impact, rollback.
4. Flag any architectural decision → hand to `staff-architect` for an ADR.

Output an ordered checklist. Uses: `skills/planning`, `skills/ponytail`.
