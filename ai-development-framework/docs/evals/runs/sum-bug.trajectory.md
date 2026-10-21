---
case: sum-bug
model: claude-opus-4-8
iterations: 2
est_tokens: 900
resolved: yes
gate: pass
---

# Trajectory — sum-bug

Reason → Act → Observe → Decide. Captured from the run that resolved this case.

## Iteration 1
- **Reason:** `task.md` wants numeric `sum`. `test.js` asserts `sum(2,2)=4`,
  `sum(-3,-4)=-7`. A subtraction bug would pass none of these.
- **Act:** ran `make eval-agent-flow CASE=sum-bug` against the shipped `solution.js`.
- **Observe:** `resolved=no`, gate=fail. `solution.js` returns `a - b`.
- **Decide:** single-line fix, no new abstraction. Continue.

## Iteration 2
- **Reason:** replace `a - b` with `a + b` — least code that works (Ponytail).
- **Act:** edited `solution.js`; re-ran the harness.
- **Observe:** `resolved=yes`, gate=pass (3/3 assertions).
- **Decide:** done — stop. Case now guards against regression of the flow.
