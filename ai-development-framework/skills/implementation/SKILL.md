---
name: implementation
description: Write the least code that works, test-first, graph-located. Use for /build.
---

# Implementation

> **Archetype:** Builder — least code that works, test-first, at production quality.

## Steps
1. **Locate precisely.** `/graphify query "where to add <thing>"` → insertion point. Avoid
   full-file reads.
2. **Test first** for non-trivial logic (one runnable check minimum).
3. **Climb the Ponytail ladder:** need it? → stdlib → native → existing dep → one line → minimum.
4. **Write it.** Shortest working diff. No scaffolding for later.
5. **Comment shortcuts.** `// ponytail: <simplification>, upgrade when <trigger>`.
6. **Run via RTK.** `rtk <build/test cmd>` — compressed output only.

## Example
> "Cache these API responses."
```python
@lru_cache(maxsize=1000)   # ponytail: stdlib cache; add TTL/eviction only if it measurably falls short
def fetch(key): ...
```
skipped: custom cache class, add when lru_cache falls short.

## Quality gates
- [ ] Test-first for non-trivial logic
- [ ] Ladder climbed; no new dep for a few-line job
- [ ] Shortcuts commented with upgrade path
- [ ] Diff is the shortest that works

## Integration
Ponytail · Graphify (locate) · RTK (run) · quality-gates (before ship).
