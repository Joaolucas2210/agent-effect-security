---
description: Implement the current slice with the least code that works.
---

# /build

Implement: **$ARGUMENTS**

Rules:
1. Graph-first: locate the exact insertion point via `/graphify query`, not full-file reads.
2. Climb the Ponytail ladder: exists? → stdlib → native → existing dep → one line → minimum.
3. Write the test first (or alongside) for non-trivial logic.
4. Mark deliberate shortcuts with `// ponytail:` and their upgrade path.
5. Shortest working diff wins. No scaffolding "for later".

Uses: `skills/implementation`, `skills/ponytail`, `skills/rtk-integration`.
