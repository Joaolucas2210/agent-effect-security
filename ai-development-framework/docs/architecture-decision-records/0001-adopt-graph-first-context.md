# ADR 0001: Graph-first context over full-file reading

- **Status:** Accepted
- **Date:** 2026-07-08
- **Deciders:** Framework maintainers

## Context
Agents burn most of their token budget re-reading whole files to rebuild context each task.
A queryable knowledge graph (Graphify) indexes code, docs, PDFs, and images once and answers
structural questions (callers, blast radius, data flow) cheaply.

## Options considered
1. **Read files on demand** — simple, but O(tokens) per task; context floods.
2. **Graph-first, files on miss** — query the graph; read files only when it's insufficient.
3. **Full RAG over embeddings only** — good for prose, weak for precise structural queries.

## Decision
Adopt **graph-first** (option 2). Every deep-analysis path queries the graph before reading.
Files are read only to confirm a specific detail the graph can't answer.

## Consequences
- Positive: large token savings; consistent mental model; faster blast-radius analysis.
- Negative: graph must stay fresh → mitigated by commit/edit hooks (`hooks/graph-update.sh`).
- Reversibility: cheap (fall back to file reads any time).

## Metrics impact
Lower token/context cost per task; no change to code complexity gates.
