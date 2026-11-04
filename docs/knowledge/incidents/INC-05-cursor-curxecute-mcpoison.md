# INC-05: CurXecute (CVE-2025-54135) and MCPoison (CVE-2025-54136), Cursor

- **Date / source:** 2025-08 · Aim Labs; Check Point Research
- **Threat:** THR-02, THR-06 · **Legs:** 2 → execution · **OWASP:** ASI04, ASI05
- **Status:** out_of_scope → covered after ADRs 0028 + 0031 · **Eval:** `eval-inc-05` (red)

## Vector

CurXecute: untrusted content makes the agent write `.cursor/mcp.json`; the IDE starts the server without a
prompt. MCPoison: a once-approved MCP entry is edited afterwards; approval is not re-asked (TOCTOU on the
config).

## Lesson

Approval must bind to a hash, not to a name. Agent-writable config that the client auto-executes is the
highest-leverage write on the machine.

## ADF

After ADR 0028: write to `.cursor/mcp.json` / `.mcp.json` denied. After ADR 0031: a server whose
`command`/`args`/tool list digest differs from the host pin is denied with `mcp_tool_list_changed`. Not covered:
Cursor is not a supported edge yet (BOUNDARY support matrix) — the pattern is covered on Claude Code / Codex.
