# ADR 0003: Closed maintenance loops are evidence-only by default

- **Status:** Accepted
- **Date:** 2026-08-19
- **Deciders:** Framework maintainers

## Context

Maintenance work needs a reliable cadence, but automatic deletion or abstraction changes can
break public entry points and architectural boundaries. The framework already has quality gates,
MCP/skill audits, Graphify freshness checks, RTK token reports, and append-only observability.

## Decision

Use one dependency-free routine runner that composes those controls. Every routine records a
Maintainer trajectory and runs the strict gates. `DRY_RUN=1` is the default. Dead-code and
abstraction findings are always suggestions; security and governance are read-only checks.
Only `routine-graph DRY_RUN=0` refreshes the local graph, and `routine-token-budget DRY_RUN=0`
adds the existing metrics snapshot. Scheduled GitHub Actions run dry and publish evidence; they
do not create commits or change source code.

## Consequences

- Positive: routine evidence is repeatable, auditable, and safe on scheduled CI.
- Positive: existing controls remain the source of truth; no new service or dependency.
- Negative: cleanup still needs a human-reviewed PR, which is intentional for high-impact changes.
- Reversibility: cheap; disable the workflow or remove a Make target without data migration.
