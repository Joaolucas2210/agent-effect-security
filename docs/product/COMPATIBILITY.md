# Compatibility and evidence

**English** · [Português (Brasil)](COMPATIBILITY.pt-BR.md)

Which edges work, on which versions, and **how we know**. A row is only as strong as its weakest
evidence level. Nothing here is "validated" without a recorded run you can open.
[BOUNDARY's support matrix](BOUNDARY.md#support-matrix) lists what each edge does not cover.

## Evidence levels

| Level | Meaning | Where it runs |
| --- | --- | --- |
| **C — contract** | A test feeds a synthetic payload, shaped like the client's, to the real hook or gateway and checks the decision | `make quality` and the `ci` workflow |
| **E — fresh clone** | `make e2e` clones the committed tree, builds a new venv and drives the real `adf` CLI with synthetic payloads on an isolated `ADF_HOME` | locally and the `ci` workflow |
| **R — real client** | The client process itself invoked the hook during a session, and the record names the client version | a host pilot, written up in `docs/product/PILOT-*` |

C and E prove ADF's side of the contract. Only R proves that a given client version actually calls
the hook with that payload. A client update can change the payload; the client version is part of the claim.

## Matrix

State at `0.2.0`. `na` means not recorded, never "probably fine".

| Edge | C | E | R — client version | Result | Evidence |
| --- | :-: | :-: | --- | --- | --- |
| Claude Code `Read` gate | ✓ | ✓ | observed, version `na` | allow README; deny `.env` and `config/.env` with a bundle; composed `cat` denied | [read hook test](../../ai-development-framework/hooks/test-adf-read-hook.py), [e2e](../../ai-development-framework/e2e/quickstart.sh), [pilot 2026-10-20, sessions 2–4](PILOT-20261020.md#what-was-done-in-order) |
| Claude Code deny-only gates (`Grep`, `Glob`, `Edit`, `Write`, `WebFetch`, selected `Bash`) | ✓ | — | `na` | denied on sensitive and agent-config paths; journal entry, no bundle | [deny gate test](../../ai-development-framework/hooks/test-adf-deny-gate.py), [Bash grammar](../../ai-development-framework/hooks/test-bash-read-grammar.py); pilot 2026-11-04 smoke used synthetic payloads ([report](PILOT-20261104.md)) |
| Codex CLI `Bash` single `cat PATH` | ✓ | ✓ | `na` (settings path documented for 0.157.0) | `cat README.md` passes, `cat config/.env` denied, composed `cat` denied | [Codex gate test](../../ai-development-framework/hooks/test-codex-bash-read-gate.py), [e2e](../../ai-development-framework/e2e/quickstart.sh) |
| A2A loopback gateway | ✓ | ✓ | n/a — ADF's own gateway and test client | effect-bound decisions over HTTP on `127.0.0.1`; HS256 pilot and RS256 + pinned JWKS | [gateway test](../../ai-development-framework/hooks/test-a2a-gateway.py), [live trial reports](../../ai-development-framework/docs/observability/trials/a2a-live/README.md) |
| MCP stdio mediated read | ✓ | — | `na` (no real Claude/Codex client run) | ADF returns snapshot bytes, `delivery_mode=mediated` | [MCP ↔ A2A client test](../../ai-development-framework/hooks/test-mcp-a2a-client.py) |
| MCP registry deny gate (Claude Code) | ✓ | — | `na`; probe checked against ADF's own server only | unregistered or drifted server/tool denied | [registry test](../../ai-development-framework/hooks/test-mcp-registry-2.py), [probe age](../../ai-development-framework/hooks/test-mcp-probe-age.py) |
| Cursor | — | — | — | no adapter | — |

The `make demo` GIF is level C: real CLI and hook, synthetic payloads, labeled as such.

## Community guarantee per integration

What the MIT Community edition guarantees, edge by edge. There is **no global enforcement**: each row holds only
while the host activation holds (hook registered and invoked, executable present, project listed in
`~/.adf/enabled-projects`; [ADR 0026](../../ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md)).

| Status | Meaning |
| --- | --- |
| **enforced** | Every call that reaches this edge gets an ADF decision before the effect; a contract test proves it |
| **partial** | Deny-only, or only some shapes get a decision; everything else passes with **no decision** |
| **unsupported** | ADF makes no decision; the client's own permissions apply |
| **unverified** | Implemented and contract-tested, but no recorded real-client run (level R) shows the client invokes it |

| Integration | Status | Mechanism | Read policy | Test |
| --- | --- | --- | --- | --- |
| Claude Code `Read` | enforced (`gate_only`) | `adf-read-hook.py` → `claude-code-read-gate.py` → PDP, PEP, snapshot read; bundle | pinned host policy, else the reference demo | [read hook test](../../ai-development-framework/hooks/test-adf-read-hook.py), [adapter test](../../ai-development-framework/hooks/test-local-read-adapter.py) |
| Claude Code `Grep`/`Glob`/`Edit`/`Write` deny gate | partial (deny-only) | `adf-deny-gate.py`: sensitive and agent-config paths denied, never an allow; `Grep`/`Glob` without `path` not covered; journal, no bundle | none: fixed sensitive-path policy | [deny gate test](../../ai-development-framework/hooks/test-adf-deny-gate.py), [journal test](../../ai-development-framework/hooks/test-deny-gate-journal.py) |
| Claude Code `Bash` | partial | single `cat PATH` decided like Codex; listed read-equivalents on sensitive paths and network after a sensitive attempt denied (ADR 0028 1b/1c); other shapes no decision | `cat`: pinned or demo; deny-only rules: none | [Bash grammar](../../ai-development-framework/hooks/test-bash-read-grammar.py), [grammar 2](../../ai-development-framework/hooks/test-bash-grammar-2.py) |
| Codex CLI `cat PATH` | enforced (`gate_only`) | `codex-bash-read-gate.py`: one allowlisted `cat` → adapter; bundle. Registration not pinned by `adf doctor` | pinned host policy, else the reference demo | [Codex gate test](../../ai-development-framework/hooks/test-codex-bash-read-gate.py) |
| Codex CLI other shell | partial (deny-only) | same deny-only grammar as Claude `Bash`; scripts, interpreters and unlisted binaries get no decision | none | [Bash grammar](../../ai-development-framework/hooks/test-bash-read-grammar.py) |
| MCP stdio read server | unverified | `mcp_read_server.py` returns adapter snapshot bytes, `delivery_mode=mediated`; no real-client run | pinned host policy, else the reference demo | [MCP ↔ A2A client test](../../ai-development-framework/hooks/test-mcp-a2a-client.py) |
| A2A loopback gateway | enforced (loopback only) | bearer verified at transport and revalidated at the effect; refuses to start reads without a valid pinned policy | pinned host policy **only**, never the demo | [gateway test](../../ai-development-framework/hooks/test-a2a-gateway.py) (`test_missing_or_tampered_host_policy_fails_closed_without_demo_grants`) |
| Claude Code subagents | partial | the same hook and gates as the main thread; principal `claude:<agent_type>` asserted by the harness, not authenticated (ADR 0023, 0033) | as the edge the subagent uses | [subagent principal test](../../ai-development-framework/hooks/test-subagent-principal.py) |
| Hook not registered, or bootstrap failure | unsupported | the wrapper and `adf hook` exit 0 with no decision; no ADF record exists | — | [failure semantics test](../../ai-development-framework/hooks/test-hook-failure-semantics.py), [CLI test](../../ai-development-framework/hooks/test-adf-cli.py) |

**Reference demo vs pinned policy.** With neither `ADF_READ_POLICY_FILE` nor `ADF_READ_POLICY_SHA256` set in the
hook's environment, the read edges marked above run the **reference demo**: it grants each requested
non-sensitive path. Sensitive paths are still denied, but it is not a reviewed allowlist. One of the two variables
alone, an empty value, a relative path, a missing or malformed file, or a pin mismatch denies every read with
`host_policy_invalid`; it never falls back to the demo. `adf doctor`, `adf hook-snippet` and
`adf projects enable` say which one is in effect ([test](../../ai-development-framework/hooks/test-demo-policy-defaults.py)).
Bundles record `policy_sha256`, not whether it came from the demo.

**`gate_only` scope.** On `gate_only` edges (Claude `Read`, Codex `cat`) ADF decides on the Git snapshot and the
client's native tool then reads the live working tree. The bundle proves the decision and a confined snapshot read,
never the bytes the native tool delivered (ADR 0026, claim C5). Where the delivered bytes must be the decided ones,
use a mediated edge.

**Principle (intent).** Community defaults are never weaker than any paid pack. A future paid offering may add
maintained content or services. It does not change what the Community edges decide for the same input.

## Reproduce

Levels C and E, from a clone, no client settings touched:

```bash
python3 -m venv .venv && source .venv/bin/activate && make install-dev
make demo          # three decisions + offline verify (C)
make e2e           # fresh clone, both hook edges, both trials (E)
```

## Record a real-client observation (level R)

Run this on a host where you own the client settings, in a throwaway repository with a fake `.env`.

1. Record the versions: `claude --version` or `codex --version`, and `git -C /path/to/adf rev-parse HEAD`.
2. Register the hook from `adf hook-snippet claude|codex` ([opt-in](QUICKSTART.md#opt-in-a-real-client-later)), restart the client, `adf projects enable /abs/throwaway`, `adf doctor --pin`; `make doctor` must exit 0.
3. In a new client session, ask for `README.md`, then `.env`.
4. `adf projects reasons` must count one `delivered/read_delivered` and one `invalid_scope`; `adf verify BUNDLE --key ~/.adf/evidence.key` must report `authenticity=valid`.
5. Add a row to a dated `PILOT-*` report with the versions, the prompts and the counts. Only then change `na` above to that version.

A missing ADF record after step 3 means the client did not call the hook: **no decision**, not a deny.
