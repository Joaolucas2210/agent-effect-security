---
description: Write/run tests and enforce coverage + mutation gates.
---

# /test

Test: **$ARGUMENTS**

Steps:
1. Cover changed logic: happy path + failure/edge paths. One check per non-trivial branch.
2. Run suite via RTK-wrapped commands (compressed output): `rtk <test-cmd>`.
3. Enforce gates (`skills/quality-gates`): changed-line coverage + **mutation score**.
4. Surviving mutants on changed code = weak tests → strengthen, don't pad line coverage.

Uses: `skills/test-review`, `skills/quality-gates`.
