# ADR 0002: Local structured observability and a GitHub-native pipeline

- **Status:** Accepted
- **Date:** 2026-08-19
- **Deciders:** Framework maintainers

## Context

The framework had eval trajectories and a metrics snapshot, but no uniform record for an
archetype hand-off, token budget, mode switch, duration, or task outcome. GitHub CI was an
optional quality-gate template instead of the default Issue → Spec → Implementation path.

## Decision

Keep observability local and append-only: `hooks/observability.sh` writes a validated JSONL
event and generates a task trajectory at completion. It records values supplied by the agent
runtime and leaves unavailable token/cost fields as `na`; it does not add a telemetry service,
provider SDK, or guessed pricing.

The GitHub workflow creates only draft documents/PRs. `/agent proceed` (or `agent:spec`) opens
a Spec PR; an authorized repository actor's `/approve-plan` is required before its merge opens
an Implementation PR; `/agent implement` marks that Builder work may start. It uses narrowly
scoped permissions, posts only a validated artifact through a separate trusted workflow, and
blocks unsafe changed-file patterns. Repository protection/rulesets must protect the workflow
and gate paths; an association check cannot prove a commenter is human.

## Consequences

- Positive: hand-offs and eval outcomes share inspectable evidence; no secret-bearing telemetry.
- Positive: a predictable GitHub workflow with human architecture/taste approval.
- Negative: an agent runtime must provide token/cost figures for them to be measured.
- Reversibility: cheap; JSONL can be exported or replaced without changing task code.
