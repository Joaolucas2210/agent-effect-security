# Product roadmap

**English** · [Português (Brasil)](ROADMAP.pt-BR.md)

Updated: 2026-10-21 · Category: *agent effect security* ([boundary](BOUNDARY.md))

This roadmap prioritizes by market pain. The engineering history (H, P0, A2A slices) remains in
[`ai-development-framework/docs/roadmap.md`](../../ai-development-framework/docs/roadmap.md). The sequencing,
the acceptance criteria, and the test commands are in the [implementation plan](IMPLEMENTATION_PLAN.md).

## Now: the sellable wedge

| Item | Pain it solves | WP |
| --- | --- | --- |
| Positioning, boundary, support matrix, one-pager | The buyer needs to understand what is covered and what stays residual | WP0 |
| Policy pack `effect-security-read-v0` | Agents read `.env`/keys; the team needs a ready policy to pin | WP1 |
| Repeatable, redacted `make a2a-live-trial` | AppSec wants reproducible deny + evidence, not a screenshot | WP2 |
| 200 + deny contract; local trial does not count A2A | A client that reads only the HTTP status treats a deny as success | WP3 |

## Next: pilot with design partners

| Item | Pain | WP |
| --- | --- | --- |
| ~~Make PDP denies that precede the scope verifiable~~ **Done 2026-10-19** | A deny of `config/.env` must be provable, not a 500 | WP1b |
| ~~RS256/JWKS runbook as an "enterprise pilot"~~ **Done 2026-10-19** ([runbook](../../ai-development-framework/docs/runbooks/a2a-rs256-jwks.md)) | HS256 does not work for a real IdP | WP4 |
| ~~OTel spans on the local edges~~ **Done 2026-10-20** ([ADR 0021](../../ai-development-framework/docs/architecture-decision-records/0021-local-edge-otel-spans.md)) | See Claude/Codex decisions on the same screen as the A2A ones | WP5 (optional) |
| Portfolio UX: `make projects` / `project-enable` / `project-disable` / `project-reasons` | AppSec enables projects and reads `reason_code` counts without editing `~/.adf` by hand | REQ-MP-02 (PR `feat/portfolio-projects-cli`) |
| Codex `cat` through the same global hook and host list | Codex users had to export root/evidence per shell | REQ-MP-03 (PR `feat/mp01-codex-symmetry`) |
| `effect_binding` in A2A pause/confirmation records ([ADR 0022](../../ai-development-framework/docs/architecture-decision-records/0022-a2a-effect-bound-confirmation.md), Accepted) | Prove offline that the human confirmation was bound to the paused effect | A2A-6b (**Done 2026-10-20**, #84) |
| A2A client on the host: the model sees `read_via_adf(path)`, never the bearer | The pilot pasted a JWT into the prompt; credential in the model's context | A2A-8 (PR `feat/mcp-a2a-client`) |
| Local principal derived from the harness (`claude:<agent_type>`) in the journal and the span ([ADR 0023](../../ai-development-framework/docs/architecture-decision-records/0023-local-principal-from-host-harness.md), Accepted) | Three subagents read in parallel and the evidence did not say who | MP-04 (PR `feat/local-principal`) |
| `principal_rules` in the pinned policy: per-agent least privilege decided by the PDP ([ADR 0024](../../ai-development-framework/docs/architecture-decision-records/0024-principal-rules-in-pinned-policy.md), Accepted) | Every principal with `workspace:read` had the same authority | MP-05 (PR `feat/principal-policy`) |
| `mint --ttl` (default 1 h) only as the pilot's IdP stand-in | Tasks expired before the human confirmation | A2A-9 (PR `feat/mint-ttl`) |
| `project-reasons` with journal attempts and per-principal counts; `POLICY=` gives granted versus unused | The root `.env` did not appear in the aggregate; privilege was not measured | MP-06 (PR `feat/project-reasons-principals`) |
| Design partner metrics (trial at the partner's SHA, aggregated `project-reasons`) | Without a partner number there is no validated thesis | Grower |

## Later: only with an `Accepted` ADR and recorded demand

| Item | Gate | WP |
| --- | --- | --- |
| Write/edit effect | Its own ADR + design partner demand | WP6 |
| DPoP/mTLS, signed Agent Card, Token Exchange with an external AS | Its own ADR (0019 deferred the endpoint) | WP7 |
| Protect `~/.adf/enabled-projects` against editing by the agent | Its own ADR; today it is a declared residual, without theater | — |
| Codex beyond `cat PATH` (`head`, `sed`, pipes) | Its own ADR + demand; full Bash coverage is not the product | — |
| Orchestrator that distributes tokens; ADF as an OAuth AS or Token Exchange endpoint; agent UI or registry | It becomes an agent platform: outside the boundary | — |
| Deterministic pre-check before the `input-required` pause (do not ask confirmation for the impossible) | ADR additive to 0018 | — |
| Skills and example in the public agent card; invalid field in the `400` | Small, but changes the card contract | — |

## Done outside the original plan

| Item | Pain | Ref |
| --- | --- | --- |
| Multi-project activation on the host (global hook + project list; host activation ≠ monorepo installation) | Use ADF across the developer's repo portfolio without copying it into each one or denying reads in bulk | REQ-MP-01 |

## Not doing

- Agent graph or orchestration UI inside the repo.
- Self-hosted Langfuse as part of the core (it is an optional sink, never an authority).
- Public bind without an ADR (the gateway listens only on `127.0.0.1`).
- Billing, phone-home telemetry enabled by default, automatic compliance certification.
- `network` or `destructive` effects.
- Cloud MCP/A2A gateway as the main narrative; installing ADF inside each client repository;
  default-on activation in every directory (opt-in allowlist only).
- Operating system sandbox, full `Bash` coverage, LLM guardian as a PDP replacement.
