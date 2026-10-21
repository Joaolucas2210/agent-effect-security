---
name: rtk-integration
description: Route terminal commands through RTK (Rust Token Killer) to compress output 60–90%. Use for every build/test/metric command.
---

# RTK Integration — output compression

> **Archetype:** Sweeper — compress command output; fewer tokens, same signal.

> Tool: https://github.com/rtk-ai/rtk — token-optimized CLI proxy.
> ⚠ Third-party. Verify install and command surface at the repo before wiring into CI.

## Principle
Never dump raw command output into context. Run it through RTK; keep the compressed signal.

## Usage
```bash
rtk --version        # verify install
rtk <cmd>            # run any dev command compressed, e.g. rtk pytest, rtk git diff
rtk gain             # show token savings analytics
rtk gain --history   # savings per command over time
rtk proxy <cmd>      # raw passthrough (debugging only)
```
In this environment a Claude Code hook auto-rewrites commands to `rtk <cmd>` — 0 tokens overhead.
See `hooks/rtk-wrap.sh`.

## Where it plugs in
- `/test`, `/ship`, quality-gates: all metric tools run under `rtk`.
- CI: wrap test/lint/coverage steps so logs don't bloat artifacts or agent context.

## Quality gates
- [ ] `rtk --version` succeeds (right binary — watch the name collision noted in RTK docs)
- [ ] Dev/metric commands run under RTK, not raw
- [ ] `rtk gain` trended in measurement-driven-improvement

## Integration
Pairs with Ponytail (less code) and Graphify (fewer reads) for the full token stack.
`hooks/rtk-wrap.sh` enforces it; `hooks/ci-quality-gates.sh` uses it.
