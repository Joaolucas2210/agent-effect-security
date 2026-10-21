# Loop: Maintainer (maintenance)

**Goal:** long-term health — security, reliability, efficiency at scale. Never simplify away a control.

## Mindset
Guard the boundaries and the invariants. The failure modes that matter are the ones that
lose data, leak secrets, or degrade under load. Skepticism is the default.

## Active
- `skills/security-review` (+ `agents/security-reviewer`) — taint, authz, secrets, deps
- `skills/quality-gates` — the enforced floor, not a suggestion
- `agents/staff-architect` — boundary direction, "should this exist", ADRs
- Audits: `make mcp-audit` · `make skill-audit` · `make graph-check`

## Gates (strictest)
All quality gates green. MCP inventory: allowlist, least privilege, no lethal-trifecta
(`docs/mcp-security.md`). No new dependency or MCP server without inventory + audit.

## Health checks
`make token-budget` (long-workflow cost) · `make metrics-snapshot` (trend) · graph freshness.

## Exit
Steady state. Regressions route back to Builder; scope changes to a human for taste.
