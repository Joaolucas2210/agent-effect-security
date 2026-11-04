# INC-02: GitHub MCP private-repo exfiltration

- **Date / source:** 2025-05 · Invariant Labs
- **Threat:** THR-03, THR-06 · **Legs:** 1, 2, 3 (full trifecta) · **OWASP:** ASI02, ASI04
- **Status:** residual · **Eval:** `eval-inc-02` (red)

## Vector

A public issue instructs the agent (via the official GitHub MCP server) to read a private repository and
publish its content in a public PR. Same token, same session, no code execution needed.

## Lesson

The trifecta is a *session* property. A single over-scoped token plus one untrusted input is enough; tool
"safety" annotations change nothing.

## ADF

Today: MCP tool output is outside the read runtime; nothing is denied. After ADR 0031 the server must be
registered; after ADR 0028 a network/write MCP call after a sensitive-adjacent read is denied in the same
run. Residual: a read of a *non-sensitive* private file followed by a PR is still allowed — ADF cannot
know the repository's secrecy from a path.
