# AI Development Framework

> **Posicionamento (2026-10):** o produto é *agent effect security*, ver
> [`docs/product/BOUNDARY.md`](../docs/product/BOUNDARY.md). O nome do diretório é histórico. Este diretório é o core de duas camadas. O **control plane**
> (PDP `tools/pdp.py`, PEP + runtime de leitura `runtime/`, evidência `integration/`, borda A2A
> `integration/a2a_gateway.py`) é o diferencial; leia [docs/CONTROL_PLANE.md](docs/CONTROL_PLANE.md) e
> [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). O conteúdo abaixo descreve o **harness** de
> adoção (skills, commands, gates, Graphify, RTK), que não é a fronteira de segurança.

Staff-level agentic development for Claude Code / Cursor / Codex.
Disciplined AI (Uncle Bob) + Minimalism (Ponytail) + Token efficiency (RTK + Graphify).

> **Core bet:** review by *metrics*, not line-by-line. Write the *least* code that works.
> Never re-read what a *knowledge graph* already knows. Keep humans in the loop for *taste*.

---

## Why this exists

| Problem | Lever | Result |
|---|---|---|
| Agents over-engineer | **Ponytail** (lazy senior dev) | up to ~94% less code generated |
| Terminal output floods context | **RTK** (Rust Token Killer) | 60–90% fewer tokens on dev ops |
| Re-reading whole files every task | **Graphify** (knowledge graph) | query the graph instead of re-reading |
| Line-by-line review doesn't scale | **Quality gates** (metrics) | coverage/complexity/mutation as the gate |
| No architectural taste | **staff-architect** + human-in-loop | trade-offs stay with humans |
| Agent hand-offs are opaque | **Observability** (JSONL + trajectories) | token/budget/switch evidence |

---

## Structure

```
ai-development-framework/
├── agents/        # reviewer + architect personas
├── commands/      # /plan /spec /build /test /review /ship /graphify ...
├── skills/        # SKILL.md per capability (planning, quality-gates, ponytail, rtk, graphify...)
├── docs/          # PRD template, ADRs, base CLAUDE.md
├── hooks/         # pre-commit + CI gates (RTK compress, Graphify staleness, Ponytail enforce)
├── rules/         # global architecture / anti-pattern / token rules
├── settings.json
├── settings.local.json
└── CLAUDE.md      # persistent rules (root)
```

---

## Default workflow: Issue → Spec PR → Implementation PR

```text
Issue + agent:spec or /agent proceed → draft Spec PR
/approve-plan (authorized repository actor) → plan-approved label
merge Spec PR                        → draft Implementation PR
/agent implement                     → Builder work may start
/build → /test → /review → /ship     → gated implementation merge
```

Install the root workflow with `make ci`. The core template remains the source of truth; see
[`docs/github-native-pipeline.md`](docs/github-native-pipeline.md) for permissions and controls.

## Builder workflow

```
/spec    → docs/PRD from a rough idea         (skills/planning)
/plan    → task breakdown + graph query       (skills/planning + graphify)
/build   → minimal implementation             (skills/implementation + ponytail)
/test    → tests + mutation + coverage gate   (skills/test-review + quality-gates)
/review  → multi-agent review (metrics first) (agents/* + skills/pr-review)
/graphify→ rebuild/update knowledge graph     (skills/graphify)
/ship    → gates pass → PR                     (hooks/ + skills/quality-gates)
```

Each `/command` maps to a skill. Reviewers run as sub-agents. Gates block the ship.

## Observability

Every archetype hand-off records its mode, dynamic switch, token input/output, remaining
sub-budget, timestamp, and duration with `make observability-record`. End a task with
`make observability-complete` to generate its trajectory, then use `make metrics` for tokens,
outcomes, estimated supplied cost, switches, and linked eval-run count. Values a runtime cannot
measure are `na`, never fabricated. See [`docs/observability/README.md`](docs/observability/README.md).
Control-plane decisions (A2A edge) can also be exported as redacted OTel spans, and
[live trials](docs/observability/trials/a2a-live/README.md) show them in Jaeger with screenshots.

---

## Install

### 1. Activate in Claude Code
Claude Code loads from `.claude/`. Link this framework in:

```bash
cd <your-project>
ln -s "$(pwd)/ai-development-framework/agents"   .claude/agents
ln -s "$(pwd)/ai-development-framework/commands"  .claude/commands
ln -s "$(pwd)/ai-development-framework/skills"    .claude/skills
# Or copy if you prefer no symlinks.
```

### 2. Ponytail (minimalism)
Already active as a Claude Code skill in this environment. Toggle:
```
/ponytail lite|full|ultra     # default: full
stop ponytail                 # off
```
Source: https://github.com/DietrichGebert/ponytail

### 3. RTK — Rust Token Killer (output compression)
```bash
rtk --version     # verify install
rtk gain          # savings analytics
```
Wired via the Claude Code hook (commands auto-rewritten to `rtk <cmd>`).
Source: https://github.com/rtk-ai/rtk

### 4. Graphify (knowledge graph)
```bash
pip install graphifyy                 # real pkg name (verified: graphifyy 0.9.10)
graphify install --platform claude    # copy the skill to the platform config (or --platform codex)
```
Then build/query the graph in-agent (there is no `graphify build` shell command):
```text
/graphify .                     # first full index → graphify-out/graph.json
/graphify query "..."           # ask the graph (--dfs to trace a path, --budget N to cap)
/graphify . --update            # re-index after changes
```
Source: https://github.com/safishamsi/graphify
Cross-tool export: `graphify install --platform claude --neo4j` (or `--falkordb`) → `graphify-out/cypher.txt`.

> ⚠ **RTK/Graphify are third-party.** Graphify's command surface here was **verified** against
> `graphifyy` 0.9.10 (build/query are the `/graphify` skill, not shell). Re-confirm versions in
> your own environment before wiring into CI.

---

## Using with each tool

- **Claude Code** — native. Skills + agents + commands + hooks load from `.claude/`.
- **Cursor** — point `.cursorrules` at `rules/` and `CLAUDE.md`; run reviewers as chat personas from `agents/`.
- **Codex** — feed `CLAUDE.md` + relevant `SKILL.md` as system context; drive commands manually.

---

## Benefits

- **Staff-level output** — architecture trade-offs, ADRs, metric-driven review.
- **Strong token economy** — Ponytail (less code) × RTK (less output) × Graphify (no re-reads).
- **Smart context** — the graph is the memory; agents query, they don't re-scan.

## Next steps
```text
/graphify .          # index the codebase (in-agent) → graphify-out/graph.json
rtk gain             # confirm RTK savings
/review              # dry-run the reviewer panel
```
