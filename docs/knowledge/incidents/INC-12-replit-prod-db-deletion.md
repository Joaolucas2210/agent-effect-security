# INC-12: Replit agent deletes a production database

- **Date / source:** 2025-07 · public account by the affected founder; Replit response
- **Threat:** THR-08 · **Legs:** execution · **OWASP:** ASI02, ASI09
- **Status:** out_of_scope · **Eval:** —

## Vector

During a declared code freeze the agent ran a destructive database command, then produced misleading
status about what it had done.

## Lesson

`destructive` effects need a gate with human confirmation bound to the exact effect (what ADR 0022 does for
A2A reads), and evidence that does not come from the agent's own narration.

## ADF

Anti-goal: ADF does not admit `destructive` or `network`. Cite to explain why the product is narrow and why
evidence must come from the control plane, never from the model.
