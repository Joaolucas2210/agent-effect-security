# Usage — auditing a project & requesting features

After `make install-into DEST=/your/project` (or `make adf-claude` at the project root),
the **first step in any project** is building the graph — everything else queries it:

```text
/graphify .            # index the code → graphify-out/graph.json (once; rebuild is automatic on edits)
```

> Rule of thumb: start with a **graph query** instead of making the agent read whole files —
> it's cheaper and surfaces the hot spots first. The human decides taste/architecture at every
> hand-off; the agent proposes.

## A. Audit the project / find improvements

You don't need to know what's wrong — the skills/agents diagnose it. Broad → specific:

| Goal | How to ask | What runs |
|---|---|---|
| "where's the bloat / what to delete" | `/ponytail-audit` | ranked whole-repo list to cut/simplify |
| "review pending changes" | `/review` (or `/code-review`) | multi-agent panel (backend/db/qa/security), metrics-first |
| "security review" | `/security-review` | taint via graph, authz, secrets, deps |
| "test quality" | skill `test-review` | mutation score + edge-case discipline |
| "metrics health / trend" | skill `measurement-driven-improvement` + `make quality` | coverage/complexity/mutation/cycles |
| "architecture / should this exist" | agent `staff-architect` | trade-offs, ADRs, high altitude |

Recommended audit flow (Maintainer / Sweeper mode):

```bash
make loop-maintenance                 # load the right mode context into the agent
```
Then in the agent:
```text
/graphify query "which modules have the most incoming dependencies?"   # find hot spots
/ponytail-audit                                                        # what to delete
/review                                                                # metrics-first review
```
Baseline the numbers:
```bash
make quality          # stack gates (coverage/complexity/mutation/cycles)
make token-budget     # token cost of workflows
make graph-check      # is the graph stale?
```

## B. Request a new feature

The command pipeline runs it from sketch to PR, each step with the right skill/gate:

```text
/spec   "add caching to the external API responses"   → minimal PRD
/plan                                                 → ordered breakdown + graph query
/build                                                → least code that works (ponytail)
/test                                                 → tests + coverage + mutation gate
/review                                               → reviewer panel
/ship                                                 → gates green + PonyTail gate → PR
```

Unsure which phase the task is in? Let the orchestrator decide:
```text
archetype-orchestrator   "add OAuth login"
```
It returns `ARCHETYPE / LOOP / ACTIVATE / GATES / NEXT`; enter the mode with `make loop-<name>`.

Shortcuts by feature size:
- **Uncertain idea / POC** → `make loop-exploration` → sketch in `sandbox/`, happy path only, throw away what doesn't prove out.
- **Real production feature** → `make loop-implementation` → `/build` + `/test`, hard gates.
- **Large feature** → start `/spec` → `/plan` (slice it), one slice at a time.

## Mental model
1. **Always** `/graphify .` first (once).
2. **Audit** → `/ponytail-audit`, `/review`, `/security-review`, `make quality`.
3. **Feature** → `/spec → /plan → /build → /test → /review → /ship`.
4. **Unsure of the phase** → `archetype-orchestrator` classifies; `make loop-<mode>` enters.
