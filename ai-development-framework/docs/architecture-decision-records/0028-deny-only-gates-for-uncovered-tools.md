# ADR 0028: deny-only gates for uncovered tools

- **Status:** Accepted for slices 1a and 1c — human acceptance on 2026-11-04 (maintainer; 1c under the wave-2 approval); slice 1b (Bash read-equivalent grammar) remains Proposed and needs its own acceptance before code.
- **Date:** 2026-11-04
- **Depends on:** ADR 0026; ADR 0008 (Accepted). Strengthened by ADR 0027 (tamper detection of this gate's own registration), not blocked by it.
- **Delivery slices:** (1a) path-only deny for `Grep`, `Glob`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit` on both path policies; (1b) Bash read-equivalent grammar; (1c) run-scoped network deny (needs the attempt journal). Each slice has its own red eval before code.
- **Scope:** `PreToolUse` hooks that can only answer `deny` or nothing. **No admit path, no byte delivery, no new effect class.**
- **Threats:** THR-01 (read-equivalent bypass), THR-02 (config-as-code execution), THR-03 (exfiltration channel).

## Problem

ADF covers `Read` on Claude Code and `cat PATH` on Codex. `Grep`, `Glob`, Bash (`head`, `sed`, `rg`,
`python -c`), `WebFetch`, `Write`/`Edit` pass through nothing. Nine of the twelve incidents in the knowledge
base enter through those tools, mostly by **writing agent configuration that later executes**
(INC-01, INC-05, INC-08, INC-10, INC-11). Building an admit path for each tool would be full Bash coverage, an
explicit anti-goal. Denying is cheaper than admitting and covers most of the Lethal Trifecta.

## Decision

- One hook, `adf-deny-gate`, registered for `Grep`, `Glob`, `Bash`, `WebFetch`, `Write`, `Edit`,
  `MultiEdit`, `NotebookEdit` (Claude) and the Codex equivalents. It evaluates **paths and tool names only**,
  never content, and answers `deny` with a reason code or returns nothing (native approval policy applies).
- Two versioned, host-pinned path policies, both metadata-only:
  - `sensitive_path_policy_v1` (existing) for read-equivalent and write tools;
  - `agent_config_policy_v1` (new) for write tools: `.claude/`, `.codex/`, `.cursor/`, `.mcp.json`,
    `.vscode/settings.json`, `.vscode/tasks.json`, `.github/workflows/`, `CLAUDE.md`, `AGENTS.md`,
    `.git/hooks/`, `~/.adf/`. Exact components, no glob DSL.
- Reason codes: `uncovered_read_denied_sensitive`, `uncovered_write_denied_sensitive`,
  `uncovered_write_denied_agent_config`, `uncovered_network_denied_after_sensitive_read`.
- `WebFetch` and `curl`/`wget`-shaped Bash are denied only when the **same run** already has a delivered
  sensitive-adjacent read in the journal (trifecta leg 3). Never by inspecting content.
- For Bash the parser recognises a closed grammar of read-equivalents (`cat`, `head`, `tail`, `sed -n`, `rg`,
  `grep`, `less`, `python3 -c` with `open(`) and path arguments; anything ambiguous → deny with
  `uncovered_bash_ambiguous`. Unknown commands return nothing.
- Every deny writes an attempt journal entry (ADR 0010) and an OTel span (ADR 0021). No bundle: no decision was admitted.

## Options considered

1. **Admit path per tool (mediated Grep/Glob)** — becomes "ADF covers Bash"; rejected (anti-goal, ROADMAP).
2. **Rely on Claude Code / Codex native permission prompts** — not pinned, not evidenced, editable by the agent (INC-08). Rejected as sole control; kept as second layer.
3. **Content-based secret detection on reads** — violates "content never authorizes"; rejected.
4. **Deny all uncovered tools** — unusable; rejected.

## Consequences

- Positive: INC-01, INC-05, INC-08, INC-10, INC-11 move from `out_of_scope` to `covered` (deny); trifecta legs 1 and 3 narrow.
- Negative: false denies on legitimate `Grep` over `secrets/` fixtures; the Bash grammar is a maintenance surface; a deny without bundle is weaker evidence than a decision.
- Reversibility: cheap (unregister hook).

## Residual risks

Path-only matching: a secret at an unlisted path is not denied. `Grep`/`Glob` **without** a `path` argument
search the whole root and can surface lines from `.env`; denying them would deny most legitimate searches, so
they pass through and stay a documented residual (mitigation is the client's ignore list, outside ADF). The
run-scoped network rule depends on the
journal, so a run with journal disabled does not trigger it. Codex `PreToolUse` sees only `Bash`. Denying
writes to `.github/workflows/` blocks legitimate CI edits; operators opt the path out per project.

## Validation

Slice 1a (delivered 2026-11-04): `hooks/adf-deny-gate.py`, `runtime/v1/policies/agent-config-policy-v1.json`,
dispatcher entries in `hooks/adf-read-hook.py`, matcher in `adf hook-snippet`. `hooks/test-adf-deny-gate.sh`
was written first and ran red (every tool fell into `unsupported_tool`); it covers INC-01, INC-05 and INC-08
shapes, symlink and `..` targets, `$ADF_HOME`, malformed input, and asserts no evidence or content access.
Slice 1a writes no journal entry and no span: a deny is visible only in the client's own output until 1b/1c
add the journal (`ponytail: journal needs new reason codes in the attempt-event enum; add with 1c`).
Slice 1c (delivered 2026-11-04): every deny-only decision, and the pre-gate `control_plane_tampered` deny, writes a
two-event attempt journal with `adapter_id: deny-only-gate` (reason codes added to the event enum; `make
project-reasons` counts them under `attempts=`). Run-scoped network rule: `WebFetch`, and Bash whose command
names `curl`/`wget`, are denied with `uncovered_network_denied_after_sensitive_read` when the same `run_id`
(session) already has a journaled attempt with reason `sensitive_path_denied`, `sensitive_argument_rejected`,
`invalid_scope`, `uncovered_read_denied_sensitive` or `uncovered_write_denied_sensitive` — i.e. the agent
*tried* to reach a secret, regardless of outcome. The signal is the journal, never content or the URL.
`hooks/test-deny-gate-journal.sh` ran red first (4 failures, 2 errors). Unreadable journals count as tainted.
Slice 1b: INC-07, INC-10 evals red before code. `make project-reasons` over the maintainer's own week:
zero `uncovered_*` denies on legitimate work is the acceptance number.

## Rollback

Remove the hook registration; the two path policies stay as data.
