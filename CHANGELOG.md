# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).
While the version is `0.x`, a minor release may change contracts; the entry says so when it does.

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

[0.1.0]: https://github.com/Joaolucas2210/agent-effect-security/releases/tag/v0.1.0
