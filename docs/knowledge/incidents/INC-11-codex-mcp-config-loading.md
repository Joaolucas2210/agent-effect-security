# INC-11: Codex CLI loads MCP configuration from an untrusted repository ⚠

- **Date / source:** 2025-10 ⚠ · CVE-2025-61260 ⚠ (verify id and advisory)
- **Threat:** THR-02, THR-06 · **Legs:** 2 → execution · **OWASP:** ASI04, ASI05
- **Status:** out_of_scope → covered after ADR 0031 · **Eval:** `eval-inc-11` (red)

## Vector

Opening a repository that ships its own MCP server configuration causes the CLI to start that server
(arbitrary command) before any trust decision.

## Lesson

Same class as INC-05: project-level agent config is code. Trust must be host-side and hash-bound.

## ADF

After ADR 0031: a server absent from the host registry is denied (`mcp_server_not_registered`); after ADR
0028 writes to the config path are denied. Codex is a supported edge (`Bash` `PreToolUse`), so the deny is
applicable once the MCP call surfaces as a tool call; the server *start* itself is the client's behaviour and
stays residual.
