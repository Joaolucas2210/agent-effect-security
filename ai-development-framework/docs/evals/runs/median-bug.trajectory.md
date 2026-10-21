---
case: median-bug
model: claude-opus-4-8
iterations: 2
est_tokens: 850
resolved: yes
gate: pass
---

# Trajectory — median-bug

Reason → Act → Observe → Decide. Captured from the run that resolved this case.

## Iteration 1
- **Reason:** `task.md` wants `median`. Tests assert `median([3,1,2])=2` (odd,
  unsorted input) and `median([1,2,3,4])=2.5` (even). Skipping the sort would
  fail the first; averaging the wrong pair would fail the second.
- **Act:** ran `make eval-agent-flow CASE=median-bug` against the shipped `solution.py`.
- **Observe:** `resolved=no`, gate=fail. Seeded bug: it indexed the *unsorted*
  list, so `median([3,1,2])` returned `1`.
- **Decide:** sort before indexing — least code that works. Continue.

## Iteration 2
- **Reason:** add `s = sorted(nums)` and index `s`; keep the even/odd branch.
- **Act:** edited `solution.py`; re-ran the harness.
- **Observe:** `resolved=yes`, gate=pass (3/3 assertions).
- **Decide:** done — stop. Case now guards the Python side of the flow.
