# INC-10: IDEsaster ⚠

- **Date / source:** 2025-12 ⚠ (verify) · security researcher disclosure covering 30+ CVEs across AI IDEs and extensions (Cursor, Windsurf, Copilot, Kiro, Zed, Cline, Roo Code, Junie) ⚠
- **Threat:** THR-01, THR-02 · **Legs:** 1, 2 · **OWASP:** ASI01, ASI02, ASI05
- **Status:** residual → covered subset after ADR 0028 · **Eval:** `eval-inc-10-*` (one per sub-pattern)

## Vector

A family: context files (rules, instructions, READMEs) carry injections; the agent then uses tool calls the
user cannot see (file reads outside the workspace, config writes, URL fetches with embedded data) to leak
secrets or gain execution. Many sub-cases reuse INC-05/INC-08 shapes.

## Lesson

The class is "context file + hidden effect". Every IDE re-implemented the same gaps; the fix is structural
(effect gating), not per-product patches.

## ADF

Per sub-pattern: reads of sensitive paths through `Read` are covered today; `Grep`/`Glob`/Bash reads and
config writes after ADR 0028; URL fetch after a sensitive read after ADR 0028. Each sub-case gets its own
eval id; the record is updated per CVE once ids are verified. Not covered: IDEs that are not supported edges.
