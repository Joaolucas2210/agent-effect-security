---
name: ponytail
description: Lazy-senior-dev minimalism. Write the least code that works; question whether it should exist at all. Reduces generated code (up to ~94%) and tokens. Active by default.
---

# Ponytail — minimalism

> **Archetype:** Sweeper — deletion over addition; the laziest solution that works.

> Official skill: https://github.com/DietrichGebert/ponytail
> Lazy means efficient, not careless. The best code is the code never written.

This framework ships with Ponytail already active as a Claude Code skill. This file is the
in-framework reference and integration contract.

## The ladder (stop at the first rung that holds)
1. **Does this need to exist?** Speculative → skip, say so. (YAGNI)
2. **Stdlib does it?** Use it.
3. **Native platform feature?** `<input type="date">` over a lib; CSS over JS; DB constraint over app code.
4. **Existing dependency solves it?** Use it. No new dep for a few lines.
5. **One line?** One line.
6. **Only then:** minimum code that works.

## Rules
- No one-impl interfaces, no factory-for-one, no config-for-a-constant.
- Deletion over addition. Boring over clever. Fewest files, shortest diff.
- Mark deliberate shortcuts: `// ponytail: <what>, upgrade when <trigger>`.
- Non-trivial logic leaves ONE runnable check behind.

## Levels
`/ponytail lite|full|ultra` — default **full**. `stop ponytail` to disable.

## When NOT to be lazy
Never simplify away: input validation at trust boundaries, error handling that prevents data
loss, security, accessibility, or anything explicitly requested. Hardware needs its calibration knob.

## Output pattern
`[code] → skipped: [X], add when [Y].`

## Integration
Governs `/build` and `/plan` scope; reviewers report Ponytail **cuts**; RTK + Graphify handle
the token side (Ponytail = less code, RTK = less output, Graphify = fewer reads).
