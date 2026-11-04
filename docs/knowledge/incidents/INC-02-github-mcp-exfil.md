# INC-02: GitHub MCP private-repo exfiltration

- **Date / source:** 2025-05 · Invariant Labs
- **Threat:** THR-03, THR-06 · **Legs:** 1, 2, 3 (full trifecta) · **OWASP:** ASI02, ASI04
- **Status:** covered since ADR 0031 `effects` + ADR 0028 1c · **Eval:** `test-mcp-effects.sh`, `test-mcp-registry.sh`

## Vector

A public issue instructs the agent (via the official GitHub MCP server) to read a private repository and
publish its content in a public PR. Same token, same session, no code execution needed.

## Lesson

The trifecta is a *session* property. A single over-scoped token plus one untrusted input is enough; tool
"safety" annotations change nothing.

## ADF

The server and its tools must be in the host registry (ADR 0031); the host declares `create_pull_request`
as `network` and `create_issue` as `write`; once the session attempted a sensitive path, those tools are denied
(`uncovered_network_denied_after_sensitive_read`) while `get_issue` stays allowed. Residual, by design: a read
of a *non-sensitive* private file followed by a PR is still allowed — ADF cannot know a repository's secrecy
from a path, and the signal is the journal, never content.
