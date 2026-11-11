# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).
While the version is `0.x`, a minor release may change contracts; the entry says so when it does.

## [Unreleased]

### Added

- `docs/product/PUBLIC-CONTRACTS.md` (+ pt-BR): versioned public surfaces (schemas, reason codes, evidence bundle,
  hook I/O, CLI exit codes, loopback A2A, experimental `PolicySource`), compatibility rules and limits.
- Tests: `hooks/test-hook-wheel-equivalence.sh` (wheel vs clone hook decisions and evidence),
  `hooks/test-a2a-policy-source.sh`, `hooks/test-config-migration-otel-flush.sh`,
  `hooks/test-config-migration-open-issues.sh` (pins today's behaviour of four open config issues).
- Community extension seam `PolicySource` (ADR 0039, Proposed): `LocalReadAdapter(..., policy_source=)` with the
  host file + pin as default; every source result is re-checked against its pin and the schemas. Default behaviour
  unchanged (`hooks/test-extension-contracts.sh`).
- Typed, stdlib-only `integration/host_config.py` mirroring every product `ADF_*` reader, secrets redacted; not wired
  into consumers yet (ADR 0040, Proposed; `hooks/test-host-config.sh`).
- `make package-check` and `hooks/test-packaging-wheel.sh`: offline sdist + wheel build, contents/metadata check,
  throwaway-venv install smoke and uninstall.
- Tests: `hooks/test-gate-only-live-path.sh`, `hooks/test-demo-policy-defaults.sh`, and characterisation tests
  `hooks/test-trust-self-integrity.sh`, `hooks/test-trust-evidence-scope.sh`, `hooks/test-bootstrap-matrix.sh`.

- **Compatibility matrix** (`docs/product/COMPATIBILITY.md`): each edge with its evidence level — contract test,
  fresh-clone e2e, or real-client observation with a recorded version — and the steps to record a real-client run.
  No row claims a real-client version that was not recorded.
- `make doctor` (read-only `adf doctor`), and `make help` now lists only the product commands in run order;
  `make help-all` keeps the full list.
- QUICKSTART: diagnose, update and roll back, including the re-pin required after pulling a new version.
- `make bootstrap`: creates `.venv` when missing (checks Python 3.10+) and installs `adf`; the first decision is
  `make bootstrap demo`, with no `source .venv/bin/activate`. The Makefile uses `.venv` automatically, and an
  explicit `ADF_CONTRACTS_PYTHON` still wins. `make test` runs the CI quality gates.
- CONTRIBUTING: a repository layout that separates the product from the development harness.

### Changed

- Hooks are importable modules (`integration/read_hook.py`, `claude_read_gate.py`, `codex_bash_read_gate.py`,
  `deny_gate.py`, `projects.py`); the `hooks/*.py` files are shims, so existing registrations keep working. `adf hook`
  and `adf projects` now work from a wheel with the same decisions and evidence as the clone. `adf doctor` and
  `adf hook-snippet` print `NOT PROTECTED` when the hook module cannot load (exit codes unchanged; the hook still makes
  no decision, ADR 0037). Pinned hosts must review and re-pin (`adf doctor --pin`) after upgrading: 5 new code labels.
- The A2A gateway reads its pinned policy once through `PolicySource` and hands the checked copy to the adapter, which
  re-checks it; a source returning no policy is refused (never the demo). Same statuses, errors and evidence.
- `otel_export` reads its flush timeout through `host_config` (first typed-config consumer; values unchanged).
- `adf version` works from a wheel install (package metadata when there is no clone `VERSION`); usage text states
  the clone vs wheel boundary. Exit codes and stdout unchanged.
- Quality gates: a self-test exiting 77 (tooling missing) is reported as a skip, never counted green (`make quality`,
  `make test-all`).
- Adding modules under `integration/` changes the control-plane snapshot: a pinned host reports
  `control_plane_tampered` until the maintainer reviews and runs `adf doctor --pin`.
- `adf doctor` reports the read policy in effect (pinned / reference demo / `host_policy_invalid`); `adf hook-snippet`
  and `adf projects enable` warn on stderr when no pinned policy is set. Exit codes and stdout JSON unchanged (R-10).
- Docs: Community guarantee per integration in COMPATIBILITY (enforced / partial / unsupported / unverified);
  ONEPAGER lists the public JWKS runbook under the MIT open core (R-14).
- Docs: ADR 0027 errata narrows the self-integrity claim to enabled projects with a present manifest; Codex
  registration is not pinned (R-08). CONTROL_PLANE/BOUNDARY separate integrity, host-key authenticity, per-attempt
  journal linking, provenance and key custody; README no longer calls the journal hash-chained (R-11). ADRs 0037/0038
  gain Phase 2A review notes and stay Proposed (R-12).
- A2A agent card reports version 0.2.0; deny gate docstring names sensitive-path policy v2.
- `make help` has two sections, *Use ADF* and *Contribute*; the harness stays under `make help-all`. The PR template
  asks what CONTRIBUTING asks: why, effect and boundary, gates with skips, risks.
- README lead names the problem with a concrete example and separates three questions: who decides, who delivers
  the bytes, and what is left to verify.

### Fixed

- `maintenance-routines.yml` checks out full history; the shallow clone failed the evidence pilot with
  `workspace_revision_unavailable`.
- `post-observability.yml` follows `ci` and validates only the first summary line; the added `evals:` line made
  every post fail.
- `implementation-ready` no longer runs its backticked text as a command substitution.

### Security

- `gate_only` reads (Claude `Read`, Codex `cat`) deny with `unsafe_file_type` when the file or a parent directory in
  the live working tree is a symlink (R-09, partial). Non-symlink paths and mediated edges are unchanged. The
  `gate_only` scope is unchanged: the bundle proves the decision, not the bytes the native tool delivered.
- **CI split by permission.** Quality gates, the fresh-clone e2e and gitleaks move to `ci.yml` with
  `contents: read` only. The Spec/Implementation PR automations move to `agentic-automation.yml`, inert until the
  owner sets `ADF_AGENTIC_AUTOMATION=true`. `hooks/test-workflow-permissions.sh` enforces both.
- The change-safety guard's `.env`/`.pem`/`.key` path check was a no-op (`! cmd` does not trip `bash -e`); it now
  fails the job. Two self-tests had the same no-op negative assertion and now fail on a forbidden match.

## [0.2.0] - 2026-11-05

Still experimental and read-only: one effect (`read`), local host only. This release closes edges that 0.1.0 left
open, makes evidence say how the bytes were delivered, and records what ADF does not see. ADR 0032 (write effect)
stays Proposed and blocked; ADRs 0037 (hook bootstrap failure) and 0038 (evidence key lifecycle) are Proposed and
change no behavior.

### Changed — contracts

- **Deny-only gates for uncovered tools** (ADR 0028). In an enabled project, `Grep`, `Glob`, `Edit`, `Write`,
  `MultiEdit` and `NotebookEdit` are denied on sensitive paths and agent configuration; Bash read-equivalent
  commands (`head`, `sed`, `grep`, pipes…) are parsed by a quote-aware grammar and denied on sensitive paths;
  network tools are denied for the rest of a run after a sensitive attempt. Every such deny writes an attempt
  journal entry and a span, not a bundle: no decision was admitted. Unknown commands are not ADF's call.
- **EvidenceBundle 1.1** (ADR 0029): `delivery_mode` is `gate_only` (the client's native tool delivers the bytes;
  the bundle does not prove them) or `mediated` (ADF delivers them). A 1.1 bundle without it fails verification;
  1.0 bundles stay valid.
- **Path rule 1.1 and `sensitive_path_policy_v2`** (ADR 0036). Root dotfiles such as `.gitignore` and `.github/`
  are readable with a bundle; `.env`, `.env.*` and `.git/**` are denied with a bundle instead of a bundle-less
  contract deny; v2 names credential files (`.npmrc`, `.netrc`, `.aws`, `.ssh`, `.config`, …) that 0.1.0 refused
  only because they started with a dot. v1 stays loadable.
- **Subagent principals** (ADR 0033): the `act` chain of a subagent is propagated and bounded by `max_act_depth`.

### Added

- **Evidence authenticity** (ADR 0030): bundles carry an HMAC under a host-held key (`adf key init`).
  `adf verify` without a key reports `authenticity=not_checked`; `--key` checks the shared-secret HMAC. It is not
  public verification.
- **Control-plane self-integrity** (ADR 0027): `adf doctor --pin` pins the installed control plane; a tampered
  checkout is denied before the gate (`control_plane_tampered`).
- **MCP registry** (ADR 0031): pinned MCP server definitions for Claude Code and Codex `config.toml`, an offline
  tool-list probe, drift and probe age in `adf doctor`; tool effects of unregistered servers are denied.
- **`make demo`**: three real decisions on a throwaway fixture (allow with a bundle, deny with a bundle, deny with
  a journal entry only), then offline verification. It touches no client settings, `~/.adf` or real secret.
- **Threat model and claims** (ADR 0026), the sensitive-path governance process (ADR 0034), a knowledge base of
  verified incidents (ADR 0035), and two host pilot reports (`docs/product/PILOT-*`).
- **Presentation**: decision-first README with the ADF identity, a presentation gate (`hooks/readme_check.py`)
  and a self-test that characterises hook failure semantics end to end.

### Fixed

- Pilot day-0 ergonomics in the CLI: tamper labels, `adf doctor` environment and clone lines, key export in the
  hook snippet.
- `adf projects reasons` no longer inflates `total=`; the journal test follows ADR 0033 depth.

### Security

- Coverage is unchanged in kind: reads outside the gated edges and supported clients are not covered, and the
  hook path is not fail-closed in general. A missing `adf` executable or a hook script that cannot load gives
  **no decision** and leaves no record; inside an enabled project, adapter failures deny. No ADF record never
  means blocked. See [docs/product/BOUNDARY.md](docs/product/BOUNDARY.md) and ADR 0037.
- `tomli` requirement raised to `>=2.5.0` (Dependabot).

## [0.1.0] - 2026-06-04

First public release. Experimental: one effect (`read`), local host only.

### Added

- **Control plane.** Deterministic PDP over closed contracts (`ToolCallIntent` → `AdmissionDecision`, ADR 0007);
  PEP that revalidates every binding at effect time and consumes the decision once (ADR 0008); confined read
  runtime over a host-prepared Git snapshot with a byte budget and a sensitive-path policy; Evidence Bundle with
  offline verification and logical replay (ADR 0009); attempt journal (ADR 0010).
- **Pinned host policy** (ADR 0011) and the policy pack `effect-security-read-v0`, which refuses to
  allowlist secrets. **Per-principal rules** (`principal_rules`, ADR 0024): a policy that names principals
  is closed to anyone it does not name.
- **Edges.** Claude Code `Read` and `Bash`, Codex `cat` (P4 grammar), MCP stdio read server (ADR 0012),
  and an A2A HTTP edge on loopback: bearer AuthN (HS256 pilot, RS256 with a pinned JWKS, ADR 0017), skill scopes,
  validated `act` delegation chains (ADR 0015), `auth-required` tasks (ADR 0016), human `input-required`
  confirmation (ADR 0018) bound to the effect with `effect_binding` (ADR 0022).
- **Host activation.** One clone, one global hook, a per-host opt-in project list (`~/.adf/enabled-projects`);
  local principal derived from the agent harness for subagents (ADR 0023); evidence outside client repos.
- **Credential outside the model.** Host-side MCP client `read_via_adf(path)`: the agent never holds the A2A bearer.
- **Operator CLI** `adf` (ADR 0025): `projects`, `hook`, `hook-snippet`, `policy build`, `a2a`, `verify`.
- **Measurement.** `adf projects reasons` counts bundles, journal attempts (including contract denies without a
  bundle) and per-principal use; with a policy it reports granted versus unused paths.
- **Observability.** Opt-in, redacted OpenTelemetry spans for A2A and local edges (ADRs 0020, 0021). Telemetry is
  a view, never the authority.
- **Trials.** `make local-evidence-trial`, `make a2a-live-trial` (repeatable, redacted reports), and `make e2e`, a
  fresh-clone release check that also runs in CI.
- **Docs.** English-first documentation with Portuguese (Brazil) siblings and a docs gate for links, anchors and
  translation parity; SECURITY, CONTRIBUTING, Code of Conduct, issue forms, CODEOWNERS, Dependabot, CITATION.

### Security

- Reads outside the gated edges (`python -c`, `head`, `sed`, pipes, other tools) are not covered. A bearer stolen
  before `exp` is valid (no DPoP/mTLS). HS256 is pilot-only. See the support matrix in
  [docs/product/BOUNDARY.md](docs/product/BOUNDARY.md#support-matrix) and report vulnerabilities as described in
  [SECURITY.md](SECURITY.md).

[0.2.0]: https://github.com/Joaolucas2210/agent-effect-security/releases/tag/v0.2.0
[0.1.0]: https://github.com/Joaolucas2210/agent-effect-security/releases/tag/v0.1.0
