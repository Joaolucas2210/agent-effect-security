# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).
While the version is `0.x`, a minor release may change contracts; the entry says so when it does.

## [Unreleased]

### Security

- **CI split by permission.** Quality gates, the fresh-clone e2e and gitleaks move to `ci.yml` with
  `contents: read` only. The Spec/Implementation PR automations move to `agentic-automation.yml`, inert until the
  owner sets `ADF_AGENTIC_AUTOMATION=true`. `hooks/test-workflow-permissions.sh` enforces both.
- The change-safety guard's `.env`/`.pem`/`.key` path check was a no-op (`! cmd` does not trip `bash -e`); it now
  fails the job. Two self-tests had the same no-op negative assertion and now fail on a forbidden match.

### Fixed

- `maintenance-routines.yml` checks out full history; the shallow clone failed the evidence pilot with
  `workspace_revision_unavailable`.
- `post-observability.yml` follows `ci` and validates only the first summary line; the added `evals:` line made
  every post fail.
- `implementation-ready` no longer runs its backticked text as a command substitution.

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
