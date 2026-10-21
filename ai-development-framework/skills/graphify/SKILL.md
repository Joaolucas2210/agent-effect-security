---
name: graphify
description: Build and query a knowledge graph of the whole codebase (code, docs, PDFs, images) so agents query instead of re-reading files. THE primary smart-context skill — consult before any deep analysis.
---

# Graphify — knowledge graph / smart context

> **Archetype:** All (cross-cutting) — every archetype queries the graph before deep reads.

> Official skill: https://github.com/safishamsi/graphify
> ⚠ Third-party. Verify the exact package name and command surface at the repo before wiring
> into CI. Commands below follow the request/vendor docs; treat as unverified until confirmed.

## Why
Re-reading whole files each task is the biggest token sink. Graphify indexes everything once
into a queryable graph; agents ask structural questions cheaply and skip full-file reads.

## Install
Shell installs the *skill*; the graph itself is built by the skill in-agent.
```bash
pip install graphifyy                 # real pkg name (verified: graphifyy 0.9.10)
graphify install --platform claude    # copy the skill to the platform config (or --platform codex)
```
Then, in-agent:
```text
/graphify .                           # first full index → writes graphify-out/graph.json
```

## Daily use — query before you read (skill `/graphify`)
```text
/graphify query "callers of PaymentService.charge"      # blast radius (BFS)
/graphify query "data flow from req.body to db" --dfs    # trace one path (DFS)
/graphify query "top files by complexity*churn"          # refactor targets
/graphify query "..." --budget 1500                      # cap answer at N tokens
/graphify . --update                                     # re-index after large changes
```
Shell tools over the built graph (`graphify-out/graph.json`):
```bash
graphify path "AuthModule" "Database"   # shortest path between two nodes
graphify explain "PaymentService"       # plain-language node explanation
graphify add https://example.com/doc    # add a URL to the corpus and update the graph
graphify install --platform claude --neo4j   # export cypher.txt (Neo4j); also --falkordb
```

## Rules (enforced in CLAUDE.md)
1. **Graph-first.** Query the graph before deep analysis; read full files only on a graph miss.
2. **Keep it fresh.** Re-run `/graphify . --update` after big changes; `hooks/graph-update.sh`
   flags staleness after edits (shell can't build — build is skill/LLM-driven).
3. **Export for tools/humans.** `--neo4j` / `--falkordb` emit `graphify-out/cypher.txt`.

## Hooks
- `PostToolUse (Edit|Write)` → `hooks/graph-update.sh` (marks the graph stale — rebuild in-agent)
- pre-commit → warns if `graphify-out/graph.json` is missing/stale (see `hooks/`)

## Quality gates
- [ ] `graphify-out/graph.json` exists and is current before `/review` and deep analysis
- [ ] Deep-analysis paths use `/graphify query`, not full-file reads
- [ ] Graph re-indexed (`/graphify . --update`) on ship
- [ ] Cross-tool export (`--neo4j`/`--falkordb`) available when needed

## Integration
Feeds every reviewer (blast radius, taint, dupes) · dependency-structure gate ·
measurement-driven-improvement (churn/complexity). The context half of the token stack
(Ponytail = less code, RTK = less output, Graphify = fewer reads).
