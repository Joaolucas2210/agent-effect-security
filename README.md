<a id="top"></a>

**English** · [Português (Brasil)](README.pt-BR.md)

<p align="center">
  <img src="docs/assets/brand/adf-mark.svg" alt="ADF mark: a request line meets an open boundary, passes a decision diamond and leaves a separate evidence square" width="72" height="72">
</p>

<h1 align="center">ADF</h1>

<p align="center"><b>Agent Effect Security</b></p>

<p align="center">
  <b>Decisions at the boundary. Evidence with explicit limits.</b><br>
  Deterministic read-policy decisions at supported, installed coding-agent tool edges.
</p>

<p align="center">
  <a href="#try-it-safely">Quickstart</a> · <a href="#coverage-and-exclusions">Coverage</a> · <a href="#trust-model-status-and-contributing">Security boundary</a>
  <br>
  <sub>experimental <code>0.x</code> — see <a href="VERSION"><code>VERSION</code></a></sub>
</p>

<p align="center">
  <a href="https://github.com/Joaolucas2210/agent-effect-security/actions/workflows/ci.yml"><img src="https://github.com/Joaolucas2210/agent-effect-security/actions/workflows/ci.yml/badge.svg?branch=main&event=push" alt="CI workflow status"></a>
  <a href="https://github.com/Joaolucas2210/agent-effect-security/releases"><img src="https://img.shields.io/github/v/release/Joaolucas2210/agent-effect-security" alt="Latest GitHub release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-263548" alt="MIT license"></a>
</p>

ADF protects **reads that pass through a supported edge you installed** — a client hook, ADF's MCP read tool or its loopback A2A gateway. It does not watch the whole host, and it is not an OS sandbox.

## The problem

A coding agent that may read `README.md` can just as easily ask to read `.env`. Permission prompts ask a person each time; traces show what happened afterwards. Neither is a deterministic authority for that file access, and neither leaves a record you can check without trusting the tool that wrote it.

ADF puts a deterministic decision at **specific installed edges**: a host-owned policy decides which reads may proceed, the decision is re-checked at the moment of the read, and the outcome has an explicit evidence path. The host operator, installed ADF code and hook registration stay trusted. [Threat model and its six bounded claims](ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md).

## See one decision

<p align="center">
  <img src="docs/assets/adf-demo.gif" alt="Terminal recording on a synthetic fixture: a Read of README.md is allowed, a Read of .env is denied with invalid_scope, adf verify checks the denial's bundle with a temporary host key, and adf projects reasons counts both decisions" width="900">
  <br>
  <sub>Synthetic fixture, real <code>adf</code> CLI and hook — not a live client session. <a href="docs/assets/README.md">How it is recorded</a>.</sub>
</p>

| Request in the GIF's fixture | Decision | Artifact | What it proves |
| --- | --- | --- | --- |
| `Read README.md` | `allow` — `delivered/read_delivered` | Evidence Bundle, `delivery_mode=gate_only` | ADF admitted the read and checked the snapshot; not the bytes a native tool would return |
| `Read .env` | `deny` — `invalid_scope` | Evidence Bundle | The policy refused the path before any read |

## Try it safely

`make demo` runs the real hook against a temporary Git fixture, a temporary `HOME` and a temporary `ADF_HOME`. It does not touch your agent settings, your `~/.adf` or any real secret, and it reports a missing decision as "no decision", never as a deny. Requirements: Git, Make, Python 3.10+ with `venv`. ADF is not published to PyPI.

```bash
python3 -m venv .venv && source .venv/bin/activate
make install-dev          # editable install into this venv; creates `adf`
make demo                 # three real decisions on a throwaway fixture, then offline verification
```

```text
  ✓ Read README.md               allow delivered/read_delivered                 Evidence Bundle
  ✓ Read .env                    deny  deny/invalid_scope                       Evidence Bundle
  ✓ Edit .claude/settings.json   deny  uncovered_write_denied_agent_config      attempt journal only
  ✓ adf verify (no key)          verified                                       authenticity=not_checked
  ✓ adf verify (demo host key)   verified                                       authenticity=valid
demo passed
```

The third decision is a deny-only gate: it leaves an **attempt journal entry only**, no bundle. The fixture, its fake `.env` and the temporary `ADF_HOME` are removed afterwards (`DEMO_KEEP=1` keeps them). The step-by-step version with the raw hook payloads is the [isolated quickstart](docs/product/QUICKSTART.md).

**Enabling a real client is a separate, opt-in step.** `adf hook-snippet claude` or `adf hook-snippet codex` **prints** JSON; it installs nothing. Review and merge its `hooks.PreToolUse` entries into the client's settings, keeping existing hooks; restart the client; run `adf projects enable /absolute/path/to/repo`; then `adf doctor --pin` once the registration is in place. For a reviewed allowlist, build a session policy and pin it with `ADF_READ_POLICY_FILE` and `ADF_READ_POLICY_SHA256`. [Opt-in and rollback](docs/product/QUICKSTART.md#opt-in-a-real-client-later). `make e2e` runs a fresh-clone contract check of the local edges and trials; it is not proof that a particular client version invoked its hook.

## How it works

1. **Edge** — a supported hook or gateway translates the agent's request into a closed intent. It never decides.
2. **PDP** — a pure function decides against a host-pinned policy: default deny, stable reason codes, no clock, no I/O, no LLM.
3. **PEP and runtime** — at the moment of the read, bindings are re-checked and the decision is consumed once; one regular file is opened by handle from a host-prepared Git snapshot, with a byte ceiling and a sensitive-path rule.
4. **Evidence** — the composed decision becomes an Evidence Bundle; an attempt refused before composition is recorded in the attempt journal.

![ADF read path: an agent intent reaches an installed edge, then PDP, PEP and a confined snapshot read. Early denies branch to a journal entry, composed decisions to a bundle, and only mediated reads return snapshot bytes](docs/assets/brand/adf-architecture.svg)

`gate_only` (Claude `Read`, supported `cat` hooks): ADF decides and checks a snapshot, then the native tool delivers its own bytes — the bundle does **not** prove those bytes. `mediated` (ADF's stdio MCP read and the A2A path): ADF returns bytes from its own controlled read. Neither mode covers a request that never reaches an installed edge. [Control plane in depth](ai-development-framework/docs/CONTROL_PLANE.md) · [policy pack](ai-development-framework/policy-packs/effect-security-read-v0/README.md).

## Coverage and exclusions

The surface implemented in this checkout. Local fixture tests and real-client observations are different levels of evidence; [BOUNDARY's support matrix](docs/product/BOUNDARY.md#support-matrix) lists grammars, versions and exceptions.

| Edge | Implemented path | What still gets through |
| --- | --- | --- |
| Claude Code | `Read` gate; selected `Bash` reads; deny-only gates on selected read, write, network and pinned MCP calls | Other Bash, script or interpreter routes; subagent tools outside these gates; client version not recorded in trials |
| Codex CLI | Hook for a supported single `cat PATH`; selected Bash denies | Other commands; MCP calls (Codex sends none to hooks); global-hook client version `na` |
| A2A | Loopback `read_workspace_file` gateway with bearer validation and effect-bound decisions | A stolen bearer stays valid until expiry; no public gateway, no DPoP/mTLS |
| MCP | ADF's stdio mediated read; Claude hook registry and definition deny gate | Unhooked servers, tool-list drift between probes, the server's own output |

No OS sandbox and no universal Bash interception are claimed. An agent with another route to the disk bypasses these gates. [Twelve real incidents mapped to covered, residual or out of scope](docs/knowledge/coverage.md).

## What evidence does — and does not — prove

![Three evidence outcomes: a gate-only bundle does not prove native bytes; a mediated bundle binds a controlled read; an early deny leaves only a journal entry](docs/assets/brand/adf-evidence-flow.svg)

| Record | Proves | Does not prove |
| --- | --- | --- |
| **Evidence Bundle** | A composed decision, its bindings and the read receipt; `delivery_mode` says whether ADF delivered bytes (`mediated`) or only gated a native tool (`gate_only`) | The bytes a native tool returned in `gate_only`; anything that never reached the edge |
| **Attempt journal** | A local, hash-chained record that an attempt reached ADF and why it was refused | A verified read; a missing hook leaves **no** ADF record at all |
| **OpenTelemetry span** (optional) | Redacted correlation for dashboards | Nothing: a span is never authorization evidence and its absence changes no decision |

`adf verify FILE` checks structure and digests offline and reports `authenticity=not_checked`. `adf verify FILE --key HOST_KEY` also checks a **shared-secret HMAC**: it authenticates against that host's key, not to an independent public verifier. Keep the key on the host; do not hand it to an external auditor. A bundle holds IDs and repository-relative scopes but never file content — review it before sharing. [Evidence boundary](docs/product/BOUNDARY.md#evidence-is-the-record-telemetry-only-visualizes) · [HMAC decision](ai-development-framework/docs/architecture-decision-records/0030-evidence-authenticity-host-key.md).

## Trust model, status and contributing

**Trust model.** The host operator must protect hook registration, the project opt-in list, policy pins and the evidence key. If the supplied wrapper cannot find the `adf` executable it exits **without a decision**; `adf hook` likewise returns no decision if it cannot load its hook script or fails before it knows the project is enabled. The client then proceeds under its own permissions. Inside an enabled project, an adapter failure is a deny. ADF does not claim global fail-closed behaviour, and an in-process deny does not contain code running outside the observed edge. [Threat model](ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md) · [boundary and trust assumptions](docs/product/BOUNDARY.md).

**Status.** Experimental `0.x`. The read effect and selected deny-only gates are implemented; a host pilot is running; the write effect is a [blocked proposal](ai-development-framework/docs/architecture-decision-records/0032-write-effect-admit-path.md) awaiting design-partner demand. `ai-development-framework/` is the development harness used to build ADF, not part of its enforcement boundary. [Roadmap](docs/product/ROADMAP.md) · [changelog](CHANGELOG.md).

**Contributing.** Start with [CONTRIBUTING](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities through the [private route in SECURITY](SECURITY.md), never in a public issue. Further reading: [host and trial guide](ai-development-framework/docs/trials.md), [OSPS Baseline self-assessment](docs/security/OSPS-BASELINE-2026-08-28.md), [brand assets](docs/brand/BRAND_GUIDELINES.md). Released under the [MIT License](LICENSE).
