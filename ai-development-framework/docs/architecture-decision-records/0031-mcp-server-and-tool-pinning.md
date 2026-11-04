# ADR 0031: MCP server and tool admission pinning

- **Status:** Accepted — slices 1 and 2, human acceptance on 2026-11-04 (maintainer). Fully delivered, with slice 2 split into a per-call and an offline part (see *Validation*).
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
Servers started outside the agent's hook path are unseen. The tool-list digest is checked only when a human runs
`adf mcp probe`: a rug-pull between probes is caught at the next probe, not at the call. Managed/enterprise MCP
settings outside the three Claude Code scopes are not read, so a server defined only there is `unverified`.
Codex drift is visible only in `adf doctor`, never at a Codex call (no hook sees it).

## Validation

Slice 1 (delivered 2026-11-04): `integration/mcp_registry.py`, the `mcp__*` branch of `hooks/adf-deny-gate.py`,
`_gate_for` in `hooks/adf-read-hook.py`, the `mcp__.*` matcher in `adf hook-snippet`, `adf mcp pin`.
Registry env: `ADF_MCP_REGISTRY_FILE` + `ADF_MCP_REGISTRY_SHA256` (json-c14n-v1, as ADR 0011). Shape is
closed to `{schema_version, servers: {name: {tools: [...]}}}`: `command`, `args` and `env` from the decision
text are **not** pinned in slice 1 because the hook cannot observe them; listing them would be documentation
pretending to be a control. `hooks/test-mcp-registry.sh` was written first and ran red (9 failures): unconfigured
= no decision, partial/wrong/swapped pin = deny all, exact names only, malformed names deny, closed shape.

Slice 2 (delivered 2026-11-04), in two parts because the `PreToolUse` payload still carries no tool list:

- **Per call — server definition.** A registry entry may pin `definition: {command, args, env_keys}` (env
  *values* are secrets and are never pinned). The deny gate reads every definition of that server the Claude
  Code client would load — `~/.claude.json` user scope, `~/.claude.json` `projects[<root>]` local scope,
  `<root>/.mcp.json` project scope — and requires **all** of them to equal the pin: `mcp_server_definition_changed`
  otherwise (INC-05 MCPoison: a repo-shipped `.mcp.json` overriding an approved server is caught);
  `mcp_server_definition_unverified` when no scope defines it or a config file is unreadable (fail closed).
  Entries without `definition` keep slice-1 behaviour.
- **Codex `config.toml` (follow-up, 2026-11-04).** `[mcp_servers.<name>]` in `~/.codex/config.toml` and
  `<root>/.codex/config.toml` (inline or sub-table `env`) is read with `tomllib` (3.11+) or the `tomli` backport
  (3.10, declared in `requirements-test.txt` and the `codex` extra); no parser → `unreadable`, never ok. Codex
  sends no MCP calls to the hook, so this is **offline**: `adf doctor` prints `mcp <server>: claude=… codex=…`
  with `ok | changed | absent | unreadable` per client and exits 1 on `changed`/`unreadable`. A Claude-origin call
  is still judged against Claude's scopes only.
- **Offline — tool-list digest.** `adf mcp probe FILE [--write]` (human-run, never from a hook) starts each
  pinned server over stdio with only its `env_keys` from the environment, lists tools, and digests
  `name + inputSchema` (descriptions and annotations excluded: they authorize nothing). Status per server:
  `no_definition | unreachable | unpinned | unchanged | mcp_tool_list_changed`; exit 1 on anything but
  `unchanged`/`no_definition`; `--write` records the digests, after which the human re-pins. A server that
  cannot be probed is never reported as unchanged.

`hooks/test-mcp-registry-2.sh` ran red first (6 failures, 2 errors) and probes the repository's own
`mcp_read_server` as the live target.

## Rollback

Delete the registry; gate returns nothing.
