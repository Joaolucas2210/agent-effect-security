# Minimalism rules (Ponytail, canonical)

Stop at the first rung that holds:
1. **Does this need to exist?** Speculative → skip, say so. (YAGNI)
2. **Stdlib does it?** Use it.
3. **Native platform feature?** `<input type="date">` over a lib; CSS over JS; DB constraint over app code.
4. **Existing dependency solves it?** Use it. No new dep for a few lines.
5. **One line?** One line.
6. **Only then:** minimum code that works.

## Always
- Fewest files, shortest diff, boring over clever.
- Mark shortcuts: `// ponytail: <what>, upgrade when <trigger>`.
- One runnable check per non-trivial logic.

## Never simplify away
Input validation at trust boundaries · error handling that prevents data loss · security ·
accessibility · anything explicitly requested · hardware calibration knobs.

See `skills/ponytail/SKILL.md` for levels (`lite|full|ultra`, default full).

## Archetype note
Minimalism is the **Sweeper** archetype's core, but it governs every mode — Builder writes
the least code that passes hard gates; Prototyper the least that resolves the unknown.
Sweeper runs `ultra` for aggressive cuts (`loops/sweeper.md`).
