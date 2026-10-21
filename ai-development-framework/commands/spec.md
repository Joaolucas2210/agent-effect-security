---
description: Turn a rough idea into a PRD (docs/PRD from template).
---

# /spec

Produce a PRD from `docs/PRD-template.md` for: **$ARGUMENTS**

Steps:
1. `/graphify query "existing features related to $ARGUMENTS"` — reuse before inventing.
2. Fill the template: problem, users, success metrics, scope, **non-goals**, risks.
3. Keep it lean (Ponytail): cut speculative requirements; mark them non-goals.
4. Save to `docs/prd-<slug>.md`. Escalate product trade-offs to a human.

Uses: `skills/planning`.
