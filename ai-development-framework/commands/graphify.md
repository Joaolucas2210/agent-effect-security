---
description: Build / update / query the codebase knowledge graph (delegates to the installed graphify skill).
---

# /graphify

This delegates to the real **graphify** skill (`pip install graphifyy`). Action: **$ARGUMENTS**

- `.` — full index of code, docs, PDFs, images → `graphify-out/graph.json`.
- `. --update` — re-index after changes.
- `query "..."` — ask the graph instead of re-reading files (default for deep analysis);
  add `--dfs` to trace one path, `--budget N` to cap the answer.
- `. --neo4j` / `. --falkordb` — export `graphify-out/cypher.txt`.

Shell tools over the built graph: `graphify path "A" "B"`, `graphify explain "X"`, `graphify add <url>`.

Always prefer `/graphify query` over full-file reads for blast radius, call sites, and
data-flow tracing. Uses: `skills/graphify`.
