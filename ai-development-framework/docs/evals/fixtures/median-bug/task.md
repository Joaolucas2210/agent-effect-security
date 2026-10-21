# Eval case: median-bug

**Goal:** `solution.py` exports `median(nums)` returning the median of a list of
numbers (odd length → middle value; even length → mean of the two middle
values). It currently ships broken (a seeded bug). Make the tests pass.

**Done criteria (objective):** `python3 -m unittest discover` exits 0.

**Constraints:** touch only `solution.py`. Ponytail: least code that works.
