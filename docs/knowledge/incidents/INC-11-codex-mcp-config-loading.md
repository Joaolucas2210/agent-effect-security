# INC-11: Codex CLI loads MCP configuration from an untrusted repository

- **Date / source:** 2025-08 (disclosed 2025-08-07, fixed 2025-08-20 in Codex CLI 0.23.0) · Check Point Research · CVE-2025-61260 (NVD entry 2026-04-14) — verified 2026-11-04
- **Threat:** THR-02, THR-06 · **Legs:** 2 → execution · **OWASP:** ASI04, ASI05
- **Status:** out_of_scope → covered after ADR 0031 · **Eval:** `eval-inc-11` (red)

## Vector

A committed `.env` sets `CODEX_HOME=./.codex`, so the CLI loads the repository's own `./.codex/config.toml` and
starts its MCP server commands without asking; anyone who runs `codex` in the clone executes them. Two
config-as-code files cooperate: an env file redirects the config root, a config file names the command.

## Lesson

Same class as INC-05: project-level agent config is code. Trust must be host-side and hash-bound.

## ADF

After ADR 0031: a server absent from the host registry is denied (`mcp_server_not_registered`), and since the
Codex follow-up `adf doctor` reads `<root>/.codex/config.toml` and reports a definition that drifts from the pin;
after ADR 0028 writes to `.codex/` and `.env` are denied. Codex is a supported edge (`Bash` `PreToolUse`), so the deny is
applicable once the MCP call surfaces as a tool call; the server *start* itself is the client's behaviour and
stays residual.
