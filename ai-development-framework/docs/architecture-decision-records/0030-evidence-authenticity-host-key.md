# ADR 0030: evidence authenticity with a host-held key

- **Status:** Proposed — awaits human acceptance.
- **Date:** 2026-11-04
- **Depends on:** ADRs 0009, 0010 (Accepted), 0027.
- **Scope:** signature over bundles, attempt journal events and A2A records. Offline verification keeps working without the key (integrity only).
- **Threats:** THR-04, THR-05; OWASP ASI10.

## Problem

`verify_offline` proves a bundle is internally consistent. It does not prove ADF produced it: any process
running as the user can write a bundle that verifies. For a design partner's investigation, "verified" must
mean "issued by this host's control plane".

## Decision

- Key: 32 random bytes in `~/.adf/evidence.key`, mode `0400`, created by `adf doctor --init-key` (human).
  HMAC-SHA256 (stdlib `hmac`) over the canonical bundle without the `signature` field.
  `ponytail: HMAC first; Ed25519 (public verification, no shared secret) when a partner needs third-party verification.`
- `signature: {alg: "hmac-sha256", key_id: sha256(key)[:16], value}` is added to the bundle, each journal
  event and each `A2AEvidenceRecord`. Missing key at write time → `evidence_signing_unavailable`, no delivery.
- `adf verify --key <path>` checks the signature; without `--key` it reports `authenticity: not_checked`.
- The key is readable only by the user; the agent runs as the user, so the key is **not** secret from the
  agent. The guarantee is: forging requires reading the key, which ADR 0028 denies at `~/.adf/` and ADR 0027
  records. Documented plainly.

## Options considered

1. **Ed25519 via `cryptography`** — new dependency; deferred as the upgrade path.
2. **Sigstore/transparency log** — network on the evidence path; rejected (offline principle).
3. **Chain hashing (each bundle references the previous)** — detects deletion, not forgery; may be added later, does not replace a key.

## Consequences

- Positive: an investigator can distinguish ADF-issued evidence from a file dropped in the directory.
- Negative: one more host secret to manage; HMAC gives no non-repudiation towards third parties.
- Reversibility: cheap (field is additive; absence is reported, not rejected, for 1.0 bundles).

## Residual risks

Same-user agent can read the key unless ADR 0028 is active. Root is out of scope.

## Rollback

Remove the signing step; `verify_offline` ignores the field.
