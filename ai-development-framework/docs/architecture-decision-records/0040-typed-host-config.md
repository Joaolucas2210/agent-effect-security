# ADR 0040: Typed host configuration

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** maintainer (pending).
- **Depends on:** ADRs 0011, 0020, 0021, 0027, 0030, 0031.
- **Scope:** how the control plane reads its `ADF_*` environment. No change to any default, reason code or exit code.

## Context
The product reads 25 `ADF_*` variables (plus `CLAUDE_PROJECT_DIR`) straight from `os.environ` in about 12 modules
(ARCH-09, R-16). The same variable gets different treatment depending on who reads it:

- `ADF_TRUSTED_REPOSITORY` falls back to the ADF clone (`read_gate_host.py:42`), to `/` (`adf-deny-gate.py:93,213`),
  to a deny (`adf-deny-gate.py:303`), or to the cwd (`cli.py:243`).
- An empty string means "absent" for `ADF_MCP_REGISTRY_*` (`mcp_registry.py:207`), but "configured and invalid" for
  `ADF_READ_POLICY_*` (`local_read_adapter.py:135`).
- `adf-read-hook.py:114-119` mutates `os.environ`. It overrides the root, but it uses `setdefault` for the revision,
  the budget and the evidence directory, so an inherited value, including an empty one, wins.
- Inherited-versus-registered precedence differs too. `control_plane_pins.host_env` lets the registered hook command
  fill an *empty* shell value. `adf doctor` lets an empty shell value win.

Nothing records all of this in one place, and reviewers have to rebuild it by grepping the code.

## Options considered
1. **Typed, pure `integration/host_config.py` that reproduces today's semantics, adopted consumer by consumer.**
   - Pros: one place to read precedence; secrets are redacted by type; every migration step can be checked for
     equivalence.
   - Cons: a second path exists until every consumer is migrated.
2. **Typed config that also normalizes the semantics** (one fallback per variable, unknown `ADF_*` rejected, empty
   string means absent everywhere).
   - Pros: simpler mental model.
   - Cons: changes behavior. For example, an empty `ADF_READ_POLICY_FILE` would switch from deny to demo. That is
     unsafe without its own review.
3. **Do nothing.** The current code works, and the inventory alone (Phase 2B report) records precedence.
   - Cons: the drift goes on, and secrets can still reach a `repr`.

## Decision
Proposed: option 1 now. Each normalization from option 2 becomes a separate, reviewed proposal. Precedence stays as
it is today:

- host-derived (`ADF_TRUSTED_REPOSITORY` in the hook) beats the inherited environment;
- the inherited environment beats the hook defaults (`setdefault`);
- the hook defaults beat the reader defaults.

`hook_environ()` is the pure form of the hook mutation. `from_env()` never raises. Values that fail lazily today
(`ADF_A2A_PORT`, `ADF_MCP_PROBE_MAX_AGE_DAYS`, `ADF_A2A_HS256_SECRET`) fail at the same access point. Secrets
(`ADF_A2A_HS256_SECRET`, `ADF_OTEL_EXPORTER_OTLP_HEADERS`, `ADF_OTEL_EXPORTER_OTLP_ENDPOINT`) are `Secret`
objects. Their repr and str are `<redacted>`.

## Consequences
- Positive: one inventory in code; tests prove equivalence (`hooks/test-host-config.sh`); diagnostics can print
  config by name without leaking values.
- Negative / debt:
  - Until migration ends, both paths exist.
  - Adding a module under `integration/` changes the control-plane snapshot (ADR 0027), so a pinned host must
    re-pin after review.
  - `ponytail:` harness variables are deliberately out of scope.
- Reversibility: cheap. The module has no consumers until a migration PR adopts it.

## Metrics impact
One new module of about 150 lines, with no new dependency. After migration, the number of `os.environ` reads in
product code drops from about 40 to a handful (`from_env(os.environ)` at each entry point).

## Phase 2C notes (2026-11-09)

Status stays **Proposed**. Nothing below changes behavior; each item is a proposal for its own reviewed PR.

**First consumer migrated.** `integration/otel_export._flush_seconds(cfg=None)` now returns
`(cfg or from_env(os.environ)).otel.flush_seconds`. It was chosen because it decides no admit or deny, sits
inside a fail-open `try`, and has no hook default or registered-env fallback. The golden matrix in
`hooks/test-config-migration-otel-flush.sh` was recorded on the old code and passes unchanged on the new one.

**Open issues, pinned as they are today** by `hooks/test-config-migration-open-issues.sh`:

| # | Today | Proposed fix | Needs its own ADR? |
|---|---|---|---|
| OI-1 | Unset `ADF_TRUSTED_REPOSITORY` means the ADF clone (`read_gate_host.py:38-42`), `/` (`adf-deny-gate.py:213`), a `host_configuration_invalid` deny (`adf-deny-gate.py:303`) or the cwd (`cli.py:247`). | One rule: outside the hook, unset means deny; `adf doctor` says "not configured" instead of probing the cwd. `RunConfig` gains one `trusted_root()` that every reader calls. | Yes. It changes deny and diagnostic outcomes. |
| OI-2 | `adf-read-hook.py:115-119` uses `setdefault`, so an exported `ADF_EVIDENCE_DIR` from another project wins and an inherited empty `ADF_TRUSTED_REVISION` survives and then denies. | The hook derives the evidence directory and ignores the inherited one, or rejects one that is not under `$ADF_HOME/evidence/<project-id>/`. An empty revision becomes `HEAD` in the hook. | Yes. It changes where evidence lands (ADR 0030/0038 scope). |
| OI-3 | An empty shell value falls through to the registered hook command in `control_plane_pins.host_env` (`control_plane_pins.py:52`, `or`), but wins in `adf doctor` (`cli.py:239`, `in`). | One helper, `merged_env(environ, registered)`, used by both. The safe direction is `in` (an explicit empty value is a configuration and is reported). | No new ADR. It is a diagnostics and pin-snapshot alignment, recorded here. |
| OI-4 | `""` means absent for `ADF_MCP_REGISTRY_*`, `ADF_EVIDENCE_KEY_FILE`, `ADF_HOME` and `ADF_OTEL_FLUSH_MS`, but configured and invalid for the read-policy pair, the JWKS pair and `ADF_TRUSTED_REVISION`. | Only "invalid everywhere" is safe for security variables. An empty read-policy value must never become the demo. Start by having `adf doctor` warn on any empty `ADF_*`. | Yes, for any runtime change. The doctor warning alone does not need one. |
