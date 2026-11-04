# ADR 0030: evidence authenticity with a host-held key

- **Status:** Accepted — human acceptance on 2026-11-04 (maintainer); previously Proposed. Implemented the same day with the two deviations recorded under *Implementation note*.
- **Date:** 2026-11-04
- **Depends on:** ADRs 0009, 0010 (Accepted), 0026; ADR 0028 slice 1a (denies agent reads of `~/.adf/`, where the key lives). Strengthened by ADR 0027, not blocked by it.
- **Scope:** signature over bundles, attempt journal events and A2A records. Offline verification keeps working without the key (integrity only).
- **Threats:** THR-04, THR-05; OWASP ASI09 (evidence a human trusts must not be forgeable).

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

## Implementation note (2026-11-04)

Two deviations from the decision text, both chosen for the smaller, more reversible diff; the maintainer
reviews them in the implementing PR:

1. **Detached signature, not an embedded field.** `integration/evidence_signing.py` writes `<file>.sig`
   (HMAC-SHA256 over the file bytes, `key_id`, `target_sha256`) next to the bundle, the A2A record and the
   completed attempt journal. Schemas 1.0, digests, `verify_offline`, `verify_record` and the trial aggregators
   (which read only `*.json`) stay byte-identical. The cost: deleting the sidecar yields `unsigned`, exactly
   like a missing field would; a 1.1 embedded field remains possible later.
2. **Opt-in by configuration, not mandatory.** Signing is on when `ADF_EVIDENCE_KEY_FILE` names a key
   (`adf key init` creates it, `0400`, 32 bytes, never overwritten). Once configured, a key that cannot be
   loaded or a sidecar that cannot be written is `evidence_signing_unavailable` (adapter), an exception mapped
   to `a2a_evidence_failed` (gateway, record removed) or `attempt_evidence_failed` (journal): no byte leaves.
   Unconfigured hosts behave exactly as before and verify as `authenticity=unsigned` with `--key`.

`adf verify FILE --key KEYFILE` reports `authenticity=valid|invalid|unsigned`; without `--key`,
`not_checked`. Exit 1 whenever integrity or (with a key) authenticity fails.

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
