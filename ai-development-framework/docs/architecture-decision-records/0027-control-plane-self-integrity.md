# ADR 0027: control-plane self-integrity

- **Status:** Proposed — awaits human acceptance.
- **Date:** 2026-11-04
- **Depends on:** ADR 0026; ADRs 0011, 0025 (Accepted).
- **Scope:** detection of tampering with ADF's own host configuration. No new effect, no admit path.
- **Threats:** THR-04 (control-plane tampering), INC-08, INC-09.

## Problem

An agent with `Bash` can today remove the hook from `.claude/settings.json`, edit `~/.adf/enabled-projects`,
replace the policy file, or run `adf projects disable`. Each is a declared residual (ADR 0025, REQ-MP-02).
Together they mean the evidence trail can be switched off silently by the thing it audits. A product whose
value is "prove" cannot leave this as prose.

## Decision

- A host-held manifest `~/.adf/pins.json` (mode `0400`, written only by `adf doctor --pin` run by the human)
  records SHA-256 of: the hook registration snippet, every gate script and `adf` entry point at the installed
  revision, the policy file, `enabled-projects`, and the JWKS file when present. Canonicalization `json-c14n-v1`.
- Every gate invocation recomputes the hashes **before** deciding. Any divergence → journal event
  `control_plane_tampered` with the divergent key names only, deny of the current call, and non-zero exit of
  `adf doctor`. The hook's fail-safe (`[ -x "$A" ] || exit 0`, ADR 0025) is replaced by a recorded
  `control_plane_missing` when the manifest exists and the gate does not.
- `make project-reasons` prints `tampered=<n>` per project; the trial aggregate gains
  `control_plane_tampered_total`.
- What the manifest does **not** protect: itself against root or the user; the agent runtime's own settings
  beyond the hook line; `.claude/settings.local.json` overrides unless pinned.

## Options considered

1. **OS protection (`chattr +i`, separate user, sandbox)** — not portable, needs root, outside boundary. Rejected.
2. **Detect only, no deny** — leaves a window where the gate still decides on a tampered policy. Rejected.
3. **Pin everything under `~/.adf` and `.claude/`** — false positives on every legitimate edit; rejected, the pinned set is closed and listed.
4. **Do nothing** — documented residual. Rejected: it empties claim C4.

## Consequences

- Positive: tampering becomes a reason code with evidence; the claim "evidence cannot be silenced by a non-root agent" becomes testable.
- Negative: operators re-pin after every legitimate change (`adf doctor --pin`); one more file in `~/.adf`.
- Reversibility: cheap (remove manifest; gates fall back to current behaviour).

## Residual risks

Root or the user can rewrite the manifest. The agent can still *read* the manifest. A tampered gate script could skip
the check itself: the manifest proves the host's intent, the check is only as trustworthy as the binary that runs
it; ADR 0030 (host-held key) is the companion.

## Validation

`hooks/test-self-integrity.sh`: remove hook line, edit `enabled-projects`, swap policy bytes with same pin,
replace gate script → each yields `control_plane_tampered` and deny; unchanged install yields no event.

## Rollback

Delete `~/.adf/pins.json` and the check; everything else unchanged.
