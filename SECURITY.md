# Security policy

**English** · [Português (Brasil)](SECURITY.pt-BR.md)

ADF is a security control for coding agents, so a vulnerability here can turn a deny into an allow. Please report
it privately and give us the chance to fix it before it is public.

## Supported versions

| Version | Supported |
| --- | --- |
| `main` and the latest `0.x` release | Yes |
| Older `0.x` releases | No; upgrade first |

The project is experimental (`0.x`). Contracts may change between minor versions, and the release notes say so.

## How to report

- Use GitHub's private reporting: **Security → Report a vulnerability** on this repository
  (<https://github.com/Joaolucas2210/agent-effect-security/security/advisories/new>).
- Do not open a public issue, pull request or discussion for a suspected vulnerability.
- Include the commit SHA, the edge involved (Claude `Read`/`Bash`, Codex `cat`, A2A, MCP), the smallest
  reproduction you have, and the `reason_code` you expected versus the one you got.
- Never send real secrets, tokens, raw Evidence Bundles from a private repository, or personal data. Redacted
  bundles and synthetic fixtures are enough.

## What to expect

| Step | Target |
| --- | --- |
| Acknowledgement | within 3 business days |
| First assessment (valid, severity, affected versions) | within 10 business days |
| Fix or mitigation for a confirmed high/critical issue | as fast as possible, coordinated with you |
| Public advisory | after a fixed release, crediting you unless you prefer otherwise |

These are goals of a single-maintainer project, not a contractual SLA.

## In scope

- A request admitted (`delivered`) that the pinned host policy, the PDP, the PEP or the runtime should deny.
- A deny or allow that leaves no Evidence Bundle or A2A record where the docs say one is written, or a bundle
  or record that verifies offline when it was tampered with.
- Authentication or authorization bypass at the A2A edge (token validation, scopes, `act` chains, task resume,
  `human:confirm`, `effect_binding`).
- Secrets, tokens, file content or absolute paths leaking into evidence, logs or OpenTelemetry spans.
- A failure in ADF that blocks an agent's tools on projects that are not enabled.

## Out of scope

These are documented limits, not vulnerabilities. See the
[support matrix](docs/product/BOUNDARY.md#support-matrix):

- Reads through tools or commands ADF does not gate (`python -c`, `head`, `sed`, pipes, other MCP servers).
- An agent editing `~/.adf/enabled-projects` or its own settings through `Bash`.
- Anything that requires the HS256 pilot secret, or a stolen bearer used before `exp` (no DPoP/mTLS yet).
- Vulnerabilities in Claude Code, Codex or other agents themselves. Report those to their vendors.
