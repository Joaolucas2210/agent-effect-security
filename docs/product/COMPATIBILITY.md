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
