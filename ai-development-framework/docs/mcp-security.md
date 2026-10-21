# MCP Security

MCP solves the N×M integration between models and data sources, but each server is an
attack surface: tool poisoning, malicious execution, secret exfiltration (refs in
`docs/roadmap.md`). "MCP with security by default" (root `CLAUDE.md`, principle 4) means
no server is adopted without an inventory entry and a declared allowlist. The contract and
the gate: `make mcp-audit` (`hooks/mcp-audit.sh`), scanning `mcp/servers.json`.

## Inventory schema

`mcp/servers.json` is `{"servers": {"<name>": { … }}}`. Per server:

| Field | Meaning | Enforcement |
| --- | --- | --- |
| `command` | executable launched (a fixed binary, not an interpreter) | **hard** if a broad interpreter (`sh`/`bash`/`zsh`/`dash`/`env`/`eval`/`python`/`node`) or not listed in `allow.commands` |
| `args` | fixed arguments | **hard** if any contains a shell metachar/wildcard (`; \| & $ \` > < *`) |
| `env` | environment passed to the server | **hard** if a secret-like key (`*TOKEN/KEY/SECRET/PASSWORD/CREDENTIAL*`) is not in `allow.env`, or if a secret value is hardcoded instead of a `${VAR}` reference |
| `allow` | `{commands, resources, scopes, env}` — the permitted surface | **hard** — audit fails if the block is absent |
| `description` | what the server does and why it's trusted | **warn** if missing/ambiguous (<20 chars) |
| `trust` | `{private_data, untrusted_content, external_comms}` booleans | **warn** if absent |
| `human_reviewed` | set `true` only after a human signs off | required to clear the trifecta gate below |

## The lethal trifecta

A server that combines **private data access + untrusted content + external communication**
can be turned into an exfiltration channel by prompt injection. When all three `trust` flags
are `true`, the audit is a **hard fail** unless `human_reviewed: true` records an explicit
human sign-off. Break the trifecta (drop one leg) or review it — don't automate past it.

## Adding a server

1. Add the entry to `mcp/servers.json` with a full `allow` block and honest `trust` flags.
2. Reference secrets as `${VAR}` — never paste values.
3. Run `make mcp-audit` until it passes.
4. If the trifecta applies, get a human sign-off and set `human_reviewed: true`.

## Validation

- `make mcp-audit` — passes on the empty inventory and on `sandbox/mcp-audit-fixture/secure-servers.json`.
- `hooks/mcp-audit.sh sandbox/mcp-audit-fixture/insecure-servers.json` — must fail (seeded defects:
  broad shell command, `curl | sh` metachars, hardcoded token, undeclared allowlist, unreviewed trifecta).
