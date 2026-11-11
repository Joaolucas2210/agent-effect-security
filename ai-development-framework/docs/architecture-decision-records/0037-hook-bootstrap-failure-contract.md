# ADR 0037: hook bootstrap failure contract

- **Status:** Proposed — no host behavior change authorized; requires human review and real-client tests.
- **Date:** 2026-11-04
- **Deciders:** maintainer (pending).
- **Depends on:** ADRs 0026, 0027, 0028 (Accepted).
- **Scope:** local hook bootstrap and client interpretation of a missing or failed ADF executable. No new effect.
- **Threats:** THR-01, THR-04.

## Problem

`adf hook-snippet` emits `[ -x "$A" ] || exit 0; exec "$A" hook`. If the binary is absent, the wrapper
returns no decision. `integration/cli.py` also catches an unexpected `adf hook` exception and returns 0 without
output. Once `adf-read-hook.py` identifies an enabled project, its internal failure path returns an explicit deny;
an unenabled project receives no decision by design. The current tests cover these Python contracts, not how
each installed client version interprets exit codes, empty output, malformed JSON, timeouts or hook registration
absence. An unconditional nonzero exit is not proven to block a tool.

## Options considered

1. **Keep the current no-decision bootstrap** — preserves availability but an enabled project's control can
   disappear before the dispatcher runs. This is the observed behavior, not a security guarantee.
2. **Emit an explicit deny from a host-owned wrapper** — can cover a missing Python package but cannot run if
   the wrapper itself is missing or unregistered; may break disabled projects without careful project lookup.
3. **Rely on client exit codes or a timeout** — smallest patch but unsafe to claim until each supported client
   version is exercised against its actual hook contract.
4. **Use an OS-level enforcement boundary** — outside ADF's scope and not a hook fix.

## Decision needed

Do not change bootstrap semantics in a documentation PR. First capture the actual Claude Code and Codex versions
and test, in a disposable `HOME` with synthetic projects: hook registered/unregistered; executable missing;
import/CLI exception; timeout; malformed payload; enabled/disabled project; pin mismatch; malformed, empty and
explicit-deny hook output. Record whether the client invokes the tool in each case, not only the hook exit code.
Require disabled projects to retain their normal behavior. Then accept an additive decision specifying the
client versions, deny format, fallback, timeout, rollback and negative tests before changing the wrapper.

## Consequences

Current behavior remains conditional: an explicit in-process deny is tested, bootstrap failure is not a global
fail-closed guarantee. An accepted follow-up may need a host-held launcher and a versioned client matrix.
No ADF evidence can prove the absence of an unobserved tool invocation.

## Validation available now

`hooks/test-adf-cli.sh` checks the current fail-safe wrapper and suppressed exception;
`hooks/test-adf-read-hook.sh` checks enabled internal failures and disabled pass-through.
`hooks/test-hook-failure-semantics.sh` (2026-11-05) characterises the whole path in one place and asserts, per
case, the client-visible answer and whether ADF left any record: **no decision and no record** for a missing
executable in the emitted wrapper (even for an enabled project), a hook script that cannot load, a failure before
the project is known to be enabled, and a project that is not enabled; **deny** for an adapter exception, an
unsupported tool and a malformed payload *when the host supplies `CLAUDE_PROJECT_DIR`*. The same malformed payload
in the Codex shape (project only from the payload's `cwd`) is **no decision**, because the project cannot be
identified. These are local fixture/contract tests. Real-client behavior for the matrix above is **not verified** in this ADR.

## Rollback

Documentation only. A later implementation must retain a host-side rollback that removes only ADF's hook
entries, preserves other hooks and does not block unenabled projects.

## Open proposal — Phase 2A review (2026-11-09)

Status stays **Proposed**; acceptance is a human decision. This review adds observed behaviour and a candidate
contract; it changes no host behaviour.

**Observed per surface** (ADF output only; how the client acts on it is not tested). Evidence:
`hooks/test-hook-failure-semantics.sh`, `hooks/test-bootstrap-matrix.sh`, `hooks/test-trust-self-integrity.sh`,
`hooks/test-a2a-gateway.sh`.

| Surface | Hook/registration missing | Executable missing | Import error | Unexpected exception | Policy missing / invalid | Pins divergent |
| --- | --- | --- | --- | --- | --- | --- |
| Claude `PreToolUse` read hook (`adf hook`) | no decision, not tested (no ADF code runs) | no decision (`exit 0`) | no decision (`cli.py`) | no decision before the project is known enabled; deny `adapter_failed` after | demo policy decides / deny `host_policy_invalid` | deny `control_plane_tampered`, only while enabled and pinned |
| Deny-only gate (inside the read hook) | as above | as above | deny `adapter_failed` (enabled) | deny `adapter_failed`; standalone bad stdin → deny | n/a (paths only) | deny before the gate |
| Codex hook (`adf hook`, `^Bash$`) | no decision, not tested | no decision (`exit 0`) | as Claude | as Claude; malformed payload without `cwd` → no decision | not tested (same adapter as Claude) | deny; Codex registration itself not pinned |
| Legacy `codex-bash-read-gate.wrapper.sh` | not tested | nonzero exit, no JSON (client reading not tested) | not tested | not tested (code: deny `adapter_failed`) | not tested | not checked |
| MCP read server (stdio) | server absent = tool absent, not tested | not tested | not tested | tool error; missing host env → `host_configuration_invalid` | as adapter | not checked |
| A2A gateway | n/a (HTTP) | n/a | not tested | not tested (hypothesis: connection closed, no response) | 503 `host_policy_invalid` | not checked |

**Candidate contract (proposal, not decided).** (1) Every state above has one named outcome per surface:
`deny`, `no_decision` or `tool_error`, documented next to the support matrix. (2) An enabled project never
receives `no_decision` from code ADF controls after the project is identified (holds today). (3) States before
that point stay `no_decision` unless a host-held launcher can identify enabled projects without the Python
package; disabled projects keep their behaviour. (4) `adf doctor` is the out-of-band signal for registration,
executable and pin state, and a fleet "enforced" metric may count only hosts where it exits 0. (5) Any change
ships with the real-client matrix from *Decision needed* recorded per client version.

**Tests still needed.** Real Claude Code and Codex runs per client version for: empty stdout, nonzero exit,
malformed JSON, timeout, unregistered hook. A2A unexpected exception at the HTTP layer. MCP server absent or
crashing at start. An `adf doctor` exit-code test for a removed registration on each client.
