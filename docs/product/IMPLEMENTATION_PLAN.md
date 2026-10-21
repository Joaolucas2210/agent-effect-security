# Implementation plan: agent effect security

**English** · [Português (Brasil)](IMPLEMENTATION_PLAN.pt-BR.md)

Updated: 2026-10-21 · Scope: wedge v1 (deny and prove sensitive reads) · Boundary: [BOUNDARY](BOUNDARY.md)

Rules that apply to every package:

- No new effect class (write, network) without its own `Accepted` ADR **and** design partner demand
  recorded in the [Registered demand](#registered-demand) table.
- Code only where it serves the wedge. A gate that did not run is *skipped*, never green.
- Gates for every PR: `make install-dev`, `bash ai-development-framework/hooks/test-a2a-gateway.sh`,
  `bash ai-development-framework/hooks/test-local-read-adapter.sh`, `make quality-check`, `make eval-required`.
- Every PR description answers: which market pain? which effect? which residual remains?

## Sequence

```text
WP0 ─▶ WP1 ─▶ WP2 ─▶ WP3          (Now)
         └─▶ WP1b ✓  WP4 ✓ WP5 ✓   (Next completed)
MP-01 ✓ ─▶ MP-02 ✓ MP-03 ✓ A2A-6b ✓ (2026-10-20)
A2A-8 ─▶ MP-04 ─▶ MP-05 ─▶ A2A-9 · MP-06   (Next in PR, 2026-10-21: credential out of the model → principal → per-principal policy → measurement)
WP6, WP7                           (Later, with ADR gate)
```

## WP0: positioning and support matrix (docs)

- **Pain:** the AppSec/Platform buyer does not know what is covered; the term "framework" sold the wrong thing.
- **Goal:** README, BOUNDARY, ONEPAGER, and ROADMAP show category, wedge, out of scope, demo, and residual.
- **Files:** `README.md`, `docs/product/{BOUNDARY,ONEPAGER,ROADMAP,IMPLEMENTATION_PLAN}.md`.
- **Tests:** `make quality-check`, `make eval-required`.
- **Done when:** the first screen of the README has category, problem, solution, demo, out of scope, and
  honesty; the matrix covers Claude `Read`, Codex `cat`, and the A2A AuthN modes.
- **Out of scope:** renaming the `ai-development-framework/` directory (it would break existing installations).

## WP1: policy pack `effect-security-read-v0`

- **Pain:** agents read `.env`, keys, and secrets; the team needs a ready, pinned, reviewable policy.
- **Goal:** generate the existing host policy (ADR 0011) from an exact allowlist, refusing secret
  paths. No parallel engine: the runtime keeps enforcing `sensitive-path-policy-v1`.
- **Files:** `ai-development-framework/policy-packs/effect-security-read-v0/{pack.json,build.py,README.md}`,
  `ai-development-framework/hooks/test-policy-pack.{sh,py}`.
- **Tests:** `bash ai-development-framework/hooks/test-policy-pack.sh`.
- **Done when:** the output loads with `load_host_policy` and the printed pin; the Claude `Read` gate delivers the
  README and denies `.env`, `config/.env`, and `secrets/…` with the `reason_code` of each layer; the pack denylist
  contains the runtime one; a secret that escaped the builder is still denied at the runtime.
- **Out of scope:** wildcard/DSL in the policy (ADR 0011 forbids it), changing the runtime denylist.

## WP1b: verifiable PDP denies that precede the scope (**Done**, 2026-10-19)

- **Pain:** `invalid_scope`, `invalid_arguments`, and `sensitive_argument_rejected` produce a bundle with
  `effective_scope: null`. The `EvidenceBundle` schema requires an object, so the bundle does not verify offline.
  Claude/Codex count these cases in `evidence_bundle_invalid_total`; A2A responds 500
  `a2a_evidence_failed` (example: `config/.env`). It is fail-closed, but the deny is not proven.
- **Goal:** accept `effective_scope: null` in the bundle schema, aligned with `AdmissionDecision`, which already
  allows `null`. An admit with `null` still fails `verify_offline`, because the receipt requires a scope.
- **Files:** `integration/v1/schemas/evidence-bundle.schema.json`, `hooks/test-local-evidence-bundle.py`,
  the pinned counts in `hooks/test-local-evidence-trial.py`, `docs/CONTROL_PLANE.md` (limits and
  interpretation), and case T5d of `hooks/run-a2a-live-trial.py` (now expects 200 `invalid_scope`).
- **Tests:** bundle, local-evidence-trial, a2a-gateway, and a2a-live-trial suites.
- **Done when:** the `config/.env` deny verifies on all three edges and the change in the pinned suite metrics
  (`evidence_bundle_invalid_total` 1 → 0) is documented in the PR.
- **Status:** approved by the maintainer and delivered. Pinned suite metrics change: `evidence_bundle_invalid_total`
  1 → 0, `deny_total` 0 → 1, `binding_mismatch_total` 1 → 2, `decisions_total` 3 → 4. Do not compare with earlier trials.
- **Out of scope:** producing a bundle for contract denies (the request never validated).

## WP2: repeatable live A2A trial

- **Pain:** a single manual trial does not convince AppSec; it must be reproducible at their SHA.
- **Goal:** `make a2a-live-trial` starts the real gateway on loopback with a hermetic fixture, the pack policy, and
  an HS256 secret in memory only, and runs the matrix: 401 (no token, invalid signature, expired),
  403 (scope, skill), policy deny, path outside the workspace, `.env` at the root and nested, README allow,
  `input-required` pause → human confirmation.
- **Files:** `ai-development-framework/hooks/run-a2a-live-trial.py`, `hooks/test-a2a-live-trial.{sh,py}`,
  `Makefile`, `docs/observability/trials/a2a-live/README.md`.
- **Tests:** `bash ai-development-framework/hooks/test-a2a-live-trial.sh`; `make a2a-live-trial`.
- **Done when:** it exits with a nonzero code if any case diverges, if a record fails
  `verify_record`, or if the report contains a token, secret, absolute path, or content; it never overwrites a trial.
- **Out of scope:** automatic Jaeger query, latency benchmark, RS256 with a real IdP.

## WP3: docs for the 200 + deny contract and the A2A count

- **Pain:** a client that reads only the HTTP status treats a deny as success; mixed aggregates mislead AppSec.
- **Goal:** document that a 200 can carry `outcome=deny` and that `make local-evidence-trial` does not count
  A2A records. The WP2 `summary.json` is the lean A2A aggregator.
- **Files:** `docs/product/BOUNDARY.md`, `docs/observability/trials/a2a-live/README.md`.
- **Tests:** `make quality-check`.
- **Done when:** both rules appear in the boundary and in the A2A trials README.
- **Out of scope:** a versioned A2A aggregator with its own schema (only when a partner needs it).

## WP4: RS256/JWKS runbook ("enterprise pilot") (**Done**, 2026-10-19)

- **Pain:** HS256 does not work for a real IdP; an enterprise partner needs a golden path.
- **Goal:** step-by-step runbook: export the IdP JWKS, compute the pin, configure `iss`/`aud`, rotate the
  key (new pin between sessions), validate with a real token, and an A2A trial with `auth_mode: rs256_jwks`.
- **Files:** `ai-development-framework/docs/runbooks/a2a-rs256-jwks.md` (new); possibly a `--jwks`
  option in the WP2 runner.
- **Tests:** `test-a2a-gateway.sh` (RS256 already has mutation and an `openssl` oracle).
- **Done when:** a partner runs the runbook without reading code and obtains an A2A trial in RS256.
- **Out of scope:** automatic JWKS fetch/rotation, token issuance by the gateway.
- **Delivered:** [`docs/runbooks/a2a-rs256-jwks.md`](../../ai-development-framework/docs/runbooks/a2a-rs256-jwks.md) and
  `make a2a-live-trial AUTH=rs256` (test IdP via `openssl`, gateway with only the pinned public JWKS). The trial with
  a real IdP is the runbook's manual smoke test: a real IdP does not issue the matrix's adversarial tokens.

## WP5: OTel spans on the local edges (**Done**, 2026-10-20; [ADR 0021](../../ai-development-framework/docs/architecture-decision-records/0021-local-edge-otel-spans.md) Accepted)

- **Pain:** Claude/Codex decisions do not appear on the same screen as the A2A ones.
- **Goal:** one `adf.local_read.request` span per decision of each local edge (Claude `Read`, Codex `cat`,
  MCP), emitted at the edge and not in the adapter (A2A keeps a single span). It uses the ADR 0020 allowlist plus
  `adf.edge`, a capped flush in the hooks, and no stderr in the hook.
- **Files:** `hooks/claude-code-read-gate.py`, `hooks/codex-bash-read-gate.py`, `integration/mcp_read_server.py`,
  `integration/otel_export.py`, `hooks/test-otel-export.py`.
- **Tests:** `test-otel-export.sh`, `test-local-read-adapter.sh`, `test-a2a-gateway.sh`.
- **Done when:** ADR 0021 is `Accepted` and its validation matrix passes: a single span per edge,
  no path/`command`/`session_id` in the payload, identical decision with the collector down, flush within the cap.
- **Out of scope:** making the span evidence; PDP/PEP child spans; any attribute beyond `adf.edge`.

## WP6: write/edit effect (Later, ADR gate)

- **Pain:** agents also edit sensitive files (CI, deploy configs).
- **Gate:** `Accepted` ADR + demand from at least one design partner recorded below.
- **Sketch:** a new effect class in the PDP, a PEP with atomic write in the worktree, a receipt with a
  before/after digest, and the Claude `Edit`/`Write` edges.
- **Out of scope until the gate:** any code.

## WP7: DPoP/mTLS, signed Agent Card, Token Exchange with an external AS (Later, ADR gate)

- **Pain:** a stolen bearer is valid until `exp`; remote peers ask for proof of possession.
- **Gate:** its own ADR (0019 deferred the exchange endpoint) + recorded demand.
- **Out of scope until the gate:** Token Exchange endpoint, DPoP, bind outside loopback.

## REQ-MP-01: multi-project activation on the host (**Done**, 2026-10-20)

- **Pain:** ADF only worked well in its own clone; a global hook without per-project configuration would deny everything.
- **Delivered:** `hooks/adf-read-hook.py` (single global registration, `~/.adf/enabled-projects` list, evidence in
  `~/.adf/evidence/`), `hooks/test-adf-read-hook.{sh,py}`, a section in `docs/trials.md`.
- **Outside the MVP:** auto-discovery of repos, automatic policy pack per project, protection of the list against
  editing via `Bash`. The Codex wrapper became MP-03.

## REQ-MP-02: portfolio UX (PR `feat/portfolio-projects-cli`, 2026-10-20)

- **Pain:** projects could be enabled only by editing `~/.adf/enabled-projects` by hand; no view of what was denied per project.
- **Delivered:** `hooks/adf-projects.py` (`list | enable | disable | reasons`) and `make projects` / `project-enable` /
  `project-disable` / `project-reasons`. Same rules as the hook (absolute, normalized, no `..`; a symlink becomes the
  real path; outside git accepted with a warning); atomic `0600` write; `reasons` aggregates `reason_code` per project
  (receipt first), counts only.
- **Tests:** `bash ai-development-framework/hooks/test-adf-projects.sh`.
- **Residual:** the agent can run the CLI or edit the file via `Bash`; the list is not protected.

## REQ-MP-03: Codex through the same global hook (PR `feat/mp01-codex-symmetry`, 2026-10-20)

- **Pain:** the host allowlist only covered Claude's `Read`; Codex required per-shell variables.
- **Delivered:** `adf-read-hook.py` dispatches `Read` → Claude gate and `Bash` → Codex P4 gate; the project comes from
  `CLAUDE_PROJECT_DIR` or from the payload's `cwd` (both from the host). Same list, git root, and evidence folder.
  An enabled project with an unknown tool or a malformed payload → deny.
- **Tests:** `bash ai-development-framework/hooks/test-adf-read-hook.sh` (Codex cases).
- **Residual:** only `cat PATH`; the Codex global hook is validated by the payload contract, not in a trial (`na`).

## A2A-6b: `effect_binding` (PR `feat/a2a-effect-binding`, ADR 0022 Accepted, merged in #84, 2026-10-20)

- **Pain:** the resume is already bound to `sub`/skill/`path` (ADRs 0016/0018), but the pause record does not carry the
  descriptor, so the auditor trusts the gateway.
- **Delivered:** `effect_binding` = digest of `sub` + skill + `path` in the pause, in the confirmed resume, and in the
  resume deny; `confirmation` requires the field in the schema.
- **Tests:** `bash ai-development-framework/hooks/test-a2a-gateway.sh`, `test-a2a-live-trial.sh`.
- **Status:** ADR 0022 accepted by the maintainer on 2026-10-20; delivered.

## A2A-8: A2A client on the host (PR `feat/mcp-a2a-client`, 2026-10-21)

- **Pain:** the pilot pasted a JWT into the prompt so the peer could read through the gateway; credential in the model's context.
- **Delivered:** `integration/mcp_a2a_client.py`, an MCP stdio server with one tool `read_via_adf(path)`; token in
  `ADF_A2A_TOKEN_FILE` (absolute, regular, `0600`), URL on loopback only; deny/pause/401/transport become reason codes;
  no confirmation tool, by design.
- **Tests:** `bash ai-development-framework/hooks/test-mcp-a2a-client.sh`.
- **Residual:** an agent that someone gives a token to can still use `curl` via `Bash`.

## MP-04: local principal derived from the harness (PR `feat/local-principal`, ADR 0023 Accepted, 2026-10-21)

- **Pain:** three subagents in parallel and the evidence did not say who read what.
- **Delivered:** `local_principal(payload, edge)` builds a `CallerPrincipal` (`claude:<agent_type>`, `host_harness`) from
  the hook payload, verified empirically; it goes to the PDP/PEP, to the journal (`principal_sub`), and to the span
  (`adf.agent_type`). A malformed `agent_type` denies. Bundle unchanged.
- **Tests:** `test-local-edge-otel.sh`, `test-adf-read-hook.sh`.
- **Status:** ADR 0023 accepted by the maintainer on 2026-10-21; delivered.

## MP-05: `principal_rules` in the pinned policy (PR `feat/principal-policy`, ADR 0024 Accepted, 2026-10-21)

- **Pain:** every principal with `workspace:read` had the same authority; per-agent least privilege did not exist in the PDP.
- **Delivered:** optional `principal_rules` in the `PolicyBundle`, covered by the pin; PDP closed to anyone not named
  (`principal_required`, `principal_not_allowlisted`, `scope_not_allowlisted_for_principal`); the host list remains
  the ceiling. `build.py --principal SUB=PATH[,PATH]`.
- **Tests:** `bash ai-development-framework/hooks/test-principal-policy.sh` (PDP, builder, A2A end to end, adapter).
- **Status:** ADR 0024 accepted by the maintainer on 2026-10-21; delivered. Depends on MP-04 to apply on the local edges; without it, a policy with
  `principal_rules` denies the local edges (`principal_required`), by design.

## A2A-9: `mint --ttl` (PR `feat/mint-ttl`, 2026-10-21)

- **Pain:** the 5 min token expired before three human confirmations could be sent in the pilot.
- **Delivered:** default 1 h, `--ttl` up to 86400, only in the IdP stand-in; the gateway still does not issue tokens.

## MP-06: `project-reasons` with journal and principals (PR `feat/project-reasons-principals`, 2026-10-21)

- **Pain:** the root `.env` (contract deny, no bundle) did not appear in the aggregate; nothing measured per-agent privilege.
- **Delivered:** an `attempts=` line from the journal; `principal=` lines with attempts/delivered/denied/paths_read; `POLICY=` gives
  `granted`/`unused` per principal. Counts only, never paths.
- **Tests:** `bash ai-development-framework/hooks/test-adf-projects.sh`.

## Explicitly not doing

Agent graph UI in the repo; self-hosted Langfuse as core; public bind without an ADR; billing;
phone-home telemetry enabled by default; orchestration UI; orchestrator that distributes tokens; ADF as an
OAuth AS or Token Exchange endpoint; agent UI or registry; token managed by the LLM.

## Registered demand

| Date | Partner | Request | WP |
| --- | --- | --- | --- |
| — | — | None registered yet | — |
