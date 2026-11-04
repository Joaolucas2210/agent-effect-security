# ADR 0026: threat model and claims

- **Status:** Proposed — awaits human acceptance.
- **Date:** 2026-11-04
- **Depends on:** ADRs 0007, 0008, 0009, 0011 (Accepted).
- **Scope:** normative. Names the attacker, the trust boundary and every claim the product may make. No code.
- **Threats:** [THR-01..THR-06](../../../docs/knowledge/threats/README.md).

## Problem

Twenty-five ADRs define mechanisms (PDP, PEP, bindings, evidence, principals) but none defines who the attacker
is, what the host is trusted for, or what "prove" means. BOUNDARY.md and CONTROL_PLANE.md carry pieces of this
in prose. Each new ADR re-argues the boundary, public text risks over-claiming, and the knowledge base
([incidents](../../../docs/knowledge/incidents/)) cannot be mapped to a coverage status without a
reference model.

## Decision

### Attacker

The attacker is **untrusted content that reaches the agent**: workspace files (including instruction and
configuration files), MCP tool output and tool descriptions, A2A peer messages, dependencies' install scripts,
web content. The attacker can make the model request any tool call. The attacker **cannot** run code on the
host outside what the agent's tools allow.

Out of the model, declared residual: the agent runtime itself (IDE/CLI vendor CVEs), the OS, a compromised
host or user account, a malicious ADF install, root.

### Trust boundary

| Trusted | Not trusted |
| --- | --- |
| Host operator: pinned policy + pin, `~/.adf/enabled-projects`, hook registration, repository + revision, evidence directory, host-held keys | Tool payload fields, file content, tool descriptions/annotations, model output, A2A body, environment variables set by the agent |
| ADF code at the installed revision | ADF code or config after the agent could write to it (ADR 0027) |
| Git snapshot digest computed by `WorkspaceManager` | The live checkout |

### Claims (the only ones allowed in public text)

| # | Claim | Mechanism | Evidence | Eval / test |
| --- | --- | --- | --- | --- |
| C1 | A `read` on a covered edge is admitted only by the host-pinned policy; content never widens it | PDP pure, `cannot_authorize` taint | `AdmissionDecision`, bundle | `test-tool-admission.sh`, `test-principal-policy.sh` |
| C2 | A decision is consumed once, at the effect, with every binding revalidated | PEP, `intent_digest`, `task_ref` | receipt | `test-runtime-read.sh` |
| C3 | A sensitive path is denied at the effect even if the policy admitted it | `sensitive_path_policy_v1` | `sensitive_path_denied` | `test-local-read-adapter.sh` |
| C4 | Every decision on a covered edge leaves a bundle that verifies offline | `compose`, `verify_offline` | bundle | `test-local-evidence-bundle.sh` |
| C5 | On `mediated` edges the bytes delivered are the snapshot bytes; on `gate_only` edges only the decision is proven | ADR 0012, ADR 0029 | `delivery_mode` | `test-local-evidence-pilot.sh` |
| C6 | A2A identity is verified at the transport and revalidated at the effect | ADRs 0013–0017 | `A2AEvidenceRecord` | `test-a2a-gateway.sh` |

Forbidden claims: "prevents prompt injection", "sandbox", "covers Bash", "incidents prevented", "compliant
with OWASP/ISO/EU AI Act", "tamper-proof" (until ADR 0027 + 0030 are Accepted and still only against a
non-root agent).

### Lethal Trifecta mapping

| Leg | ADF today | After ADR 0028 | Never (anti-goal) |
| --- | --- | --- | --- |
| 1. Private data | `Read` (Claude), `cat` (Codex), A2A, MCP mediated read | + deny-only on `Grep`/`Glob`/Bash read-equivalents over sensitive paths | Full Bash coverage |
| 2. Untrusted content | Tainted, `cannot_authorize` | Instruction/config files classified untrusted | Content classification, LLM judge |
| 3. Exfiltration | Nothing | Deny-only on `WebFetch`/`curl`-shaped Bash when a sensitive read happened in the run (**not** by content) | `network` admit path |

### OWASP Top 10 for Agentic Applications 2026 mapping

| ASI | ADF position |
| --- | --- |
| ASI01 Goal/instruction hijack | Residual. Only the *effect* of a hijack is gated. |
| ASI02 Tool misuse | Covered on covered edges (C1–C3). |
| ASI03 Identity & privilege abuse | Covered for A2A and `principal_rules`; local principal is asserted by the harness. |
| ASI04 Supply chain (agents/tools) | Residual; ADR 0031 for MCP; agent vendor out of scope. |
| ASI05 Unexpected code execution | Residual; ADR 0028 denies config-as-code writes. |
| ASI06 Memory/context poisoning | Out of scope. |
| ASI07 Inter-agent trust | Covered on A2A (`act`, `aud`); local subagents ADR 0033. |
| ASI08 Cascading failures | Out of scope. |
| ASI09 Human-in-the-loop | Partial (`input-required`, effect-bound). |
| ASI10 Insufficient logging / repudiation | Covered for integrity (C4); authenticity after ADR 0030. |

## Options considered

1. **Keep the model in BOUNDARY.md** — no ADR gate on claims; rejected, prose is not a decision record.
2. **Adopt an external framework wholesale (MAESTRO, OWASP) as the model** — too broad for one effect; rejected, mapped instead.
3. **Formal model (IFC labels, CaMeL-style)** — more than the product does; rejected, cited as research ([PAP-04](../../../docs/knowledge/papers/README.md), [PAP-07](../../../docs/knowledge/papers/README.md)).

## Consequences

- Every ADR that adds an effect or moves the boundary must cite a `THR-` id and update the claims table.
- Every incident record carries `covered | residual | out_of_scope` against this model.
- Public material uses only C1–C6 wording.
- Reversibility: cheap (document).

## Residual risks

The model assumes the host operator is not the attacker. The local principal is asserted, not proven. Claims
C1–C4 hold only on covered edges; the agent has other read paths (BOUNDARY support matrix).

## Rollback

Delete the file; BOUNDARY.md keeps the informal description.
