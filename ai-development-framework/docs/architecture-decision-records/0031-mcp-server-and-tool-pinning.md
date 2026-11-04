# ADR 0031: MCP server and tool admission pinning

- **Status:** Proposed — awaits human acceptance.
- **Date:** 2026-11-04
- **Depends on:** ADRs 0007, 0011 (Accepted), 0026.
- **Scope:** host registry for MCP servers consumed by the agent; tool descriptions as untrusted input. No new effect.
- **Threats:** THR-06 (tool poisoning / rug-pull), INC-02, INC-05, INC-11; OWASP ASI04.

## Problem

`hooks/mcp-audit.sh` audits a server list, but nothing stops a tool description or annotation from changing
after approval, nor a repository from shipping its own `.mcp.json` that the client auto-loads (INC-05, INC-11).
The PDP already requires an exact `ToolProfile` match; MCP servers are not profiled.

## Decision

- Host registry `~/.adf/mcp-registry.json`, pinned by SHA-256 like the policy (ADR 0011): per server
  `command`, `args`, `env` keys (not values), and `tools_sha256` = digest of the canonical tool list
  (`name`, `inputSchema`) at approval time. Descriptions are **excluded** from the digest and never read for
  decisions; they are `cannot_authorize`.
- A `PreToolUse` deny-only gate (ADR 0028 family) denies any `mcp__*` call whose server is absent from the
  registry (`mcp_server_not_registered`) or whose live tool list digest differs (`mcp_tool_list_changed`).
  Re-pin is a human action (`adf mcp pin`).
- Slices: (1) server and tool **names** from the `mcp__<server>__<tool>` tool name, pinned per host — needs
  nothing from the client; (2) `tools_sha256` over `inputSchema`, only once a client exposes the live tool
  list to the hook (today the `PreToolUse` payload does not carry it: slice 2 is `skipped`, never assumed).
- Project-level `.mcp.json` / `.cursor/mcp.json` are in `agent_config_policy_v1` (ADR 0028): writes denied.

## Options considered

1. **Trust client-side approval UI** — not pinned, bypassed in INC-05. Rejected as sole control.
2. **Full MCP proxy mediating every call** — becomes an MCP gateway product; anti-goal. Rejected.
3. **Hash descriptions too** — every benign description edit re-pins; rejected, descriptions carry no authority anyway.

## Consequences

- Positive: rug-pull and repo-shipped servers become a reason code; INC-05/INC-11 → `covered` (deny).
- Negative: the gate needs the live tool list (one `tools/list` per session, cached by digest); first-run friction.
- Reversibility: cheap.

## Residual risks

A registered server can still return malicious *output*; that is leg 2 of the trifecta and stays tainted, not blocked.
Servers started outside the agent's hook path are unseen.

## Rollback

Delete the registry; gate returns nothing.
