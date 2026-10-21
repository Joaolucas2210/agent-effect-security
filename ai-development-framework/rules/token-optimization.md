# Token optimization rules

The three-layer token stack — apply all three, always:

| Layer | Tool | Rule |
|---|---|---|
| Less code | **Ponytail** | shortest working diff; delete over add |
| Less output | **RTK** | run every dev/metric command as `rtk <cmd>`; never paste raw logs |
| Fewer reads | **Graphify** | `/graphify query` before reading whole files |

## Operating rules
1. **Graph-first.** Deep analysis starts with a graph query. Full-file reads only on a miss.
2. **Compress at the source.** Wrap commands in RTK; summarize tool output to the decision-relevant signal.
3. **Write less.** Every line is future context and maintenance. Climb the Ponytail ladder.
4. **Measure it.** Track `rtk gain` and graph-hit rate in `skills/measurement-driven-improvement`.

## Don't
- Read a file to answer a question the graph can answer.
- Keep tool output in context after extracting the answer.
- Add abstraction that generates more code to maintain.

## Archetype note
The **Sweeper** archetype owns this rule and auto-activates RTK + Graphify for aggressive
sweeps (`loops/sweeper.md`). In long workflows, watch cost with `make token-budget`
(`rtk gain` + graph-hit-rate). Every archetype still applies all three layers.
