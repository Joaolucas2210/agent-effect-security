# INC-10: IDEsaster

- **Date / source:** 2025-12 (early December) · researcher Ari Marzouk · 30+ vulnerabilities, 24 CVEs assigned, across GitHub Copilot, Cursor, Windsurf, Kiro, Zed, Roo Code, Junie, Cline, Gemini CLI and Claude Code; example ids reported by secondary sources: CVE-2025-49150 and CVE-2025-61590 (Cursor), CVE-2025-53097 and CVE-2025-58372 (Roo Code), CVE-2025-58335 (Junie), CVE-2025-64660 (Copilot); AWS advisory AWS-2025-019 — disclosure verified 2026-11-04, per-CVE ids ⚠ (secondary sources only)
- **Threat:** THR-01, THR-02 · **Legs:** 1, 2 · **OWASP:** ASI01, ASI02, ASI05
- **Status:** residual → covered subset after ADR 0028 · **Eval:** `eval-inc-10-*` (one per sub-pattern)

## Vector

A family: context files (rules, instructions, READMEs) carry injections; the agent then uses tool calls the
user cannot see (file reads outside the workspace, config writes, URL fetches with embedded data) to leak
secrets or gain execution. Many sub-cases reuse INC-05/INC-08 shapes. A documented example: the agent writes a
JSON file referencing a remote schema and the IDE (VS Code, JetBrains, Zed) fetches it automatically, leaking
parameters embedded in the URL — a write that the IDE turns into a network effect.

## Lesson

The class is "context file + hidden effect". Every IDE re-implemented the same gaps; the fix is structural
(effect gating), not per-product patches.

## ADF

Per sub-pattern: reads of sensitive paths through `Read` are covered today; `Grep`/`Glob`/Bash reads and
config writes after ADR 0028; URL fetch after a sensitive read after ADR 0028. Each sub-case gets its own
eval id; the record is updated per CVE once ids are verified. Not covered: IDEs that are not supported edges.
