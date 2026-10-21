# Diagnostic: repository vs product plan

**English** · [Português (Brasil)](DIAGNOSTIC-20261020.pt-BR.md)

Date: 2026-10-20 · Base: `main` at `91fcd18` · Category: *agent effect security* ([boundary](BOUNDARY.md))

Goal: compare what is in `main` with the [roadmap](ROADMAP.md) and the [plan](IMPLEMENTATION_PLAN.md),
list gaps, regressions, residual risks and flaky tests, and decide what is still worth implementing
without leaving the wedge (deny and prove sensitive reads on the developer's host).

## Gates run on this base

| Gate | Result |
| --- | --- |
| `test-a2a-gateway.sh` (50) · `test-local-read-adapter.sh` (22) · `test-adf-read-hook.sh` (7) | green |
| `test-codex-bash-read-gate.sh` (2) · `test-policy-pack.sh` (5) · `test-local-edge-otel.sh` (6) · `test-a2a-live-trial.sh` (3) | green |
| `test-run-events.sh` (18) | green in this run; the reported flakiness did not reproduce |
| `make quality-check` · `make eval-required` | green (JS coverage, madge and stryker remain *skipped* because the tools are absent, as before) |

## Checks

| Check | Status | Evidence |
| --- | --- | --- |
| Wedge integrity (`read` effect only) | OK | The PDP denies `write`/`network`/`destructive`/`secrets` with `effect_not_supported_in_h2_02`; no new edge; the gateway stays on `127.0.0.1` only (`make_server` rejects any other host). |
| WP1b: PDP deny before scope verifies offline | **Closed** | The bundle schema accepts `effective_scope: null` (#75); T5d of the live trial expects `200 invalid_scope`; CONTROL_PLANE already describes the narrow limit (admit with `null` scope remains invalid). Documented residual: contract denies (`invalid_referenced_contract`, A2A 400) do not produce a bundle, because the request never validated. |
| REQ-MP-01: fail-safe, non-git, allowlist | OK, with a UX gap | Fail-safe lives in the registration line (`[ -f … ] || exit 0`), not in the repo; a listed project without git → `deny project_not_git`; a non-canonical line never activates. **Gap:** enabling/disabling only by editing `~/.adf/enabled-projects` by hand; there is no aggregate view of the reason codes in `~/.adf/evidence/`. |
| Local OTel + A2A | OK | `test-local-edge-otel` proves an identical decision with the collector down/failing; payload without path/`command`/`session_id` (ADR 0021). Spans are not authority (BOUNDARY). |
| Trials | OK | `make a2a-live-trial` has a green self-test; multi-project pilot documented in `trials.md`. Live trial not rerun in this diagnostic (optional). |
| Flaky `test-run-events` | not reproduced | 18/18 green in one run. If it fails again, open an issue and fix it in an isolated PR; do not mix it with a feature. |
| Docs drift | small | ROADMAP "Next" already marks WP1b/WP4/WP5 as done; the items below and the partner operations one-pager are still to be recorded. |

## Open gaps (goal priority)

| Item | Status in `main` | Decision |
| --- | --- | --- |
| P0 · Prove the deny (WP1b) | delivered in #75 | nothing to do |
| P0 · Portfolio UX (list/enable/disable + reason code aggregate) | absent | implement: `hooks/adf-projects.py` + `make projects*` (separate PR) |
| P1 · Codex symmetry for MP-01 | absent (`trials.md`: "Codex does not yet have the equivalent wrapper") | implement: `adf-read-hook.py` dispatches `Bash`→Codex gate through the same allowlist and host evidence (separate PR) |
| P1 · Effect-bound step-up | **almost delivered** (ADRs 0016/0018): resumption requires the same `sub`, skill, `path`, TTL 300 s, single use; `task_binding_mismatch` tested | gap: the pause record does not carry the effect descriptor, so the auditor cannot prove offline that what was confirmed is what was paused. Implement `effect_binding` (digest) in the pause and resume records, additive ADR |
| P2 · Docs | small drift | update ROADMAP/PLAN/ONEPAGER/BOUNDARY at the end |

## Residual risks (remain, documented)

- The agent can edit `~/.adf/enabled-projects` through `Bash`; the list takes the switch out of the workspace, it does not protect it.
- Claude covers only `Read`; Codex only allowlisted `cat PATH`; no gate is a host sandbox.
- A stolen A2A bearer is valid until `exp`; HS256 is pilot only.
- Pre-decision (A2A 400/401, contract deny) still has no record/bundle.

## Out of this cycle

WP6 (write), WP7 (DPoP/mTLS/Token Exchange), cloud UI/gateway, installing ADF in each repo,
global default-on. Any of them comes in only with an `Accepted` ADR and demand recorded in the plan.
