# ADR 0038: evidence key lifecycle and independent verification

- **Status:** Proposed — current HMAC scheme is unchanged; human review and an external audit use case required.
- **Date:** 2026-11-04
- **Deciders:** maintainer (pending).
- **Depends on:** ADRs 0009, 0010, 0026, 0030 (Accepted).
- **Scope:** key rotation, revocation and third-party verification of existing evidence. No cryptographic implementation.
- **Threats:** THR-04, THR-05.

## Problem

ADR 0030 signs bundle, A2A record and completed journal files with detached HMAC-SHA256 sidecars when
`ADF_EVIDENCE_KEY_FILE` is configured. `adf verify --key` checks with the same secret. A verifier that receives
the key can also forge records, so this is not a public signature or independent non-repudiation. The current
CLI creates one 32-byte key and refuses overwrite; it has no rotation, revocation, historical key lookup or
external auditor trust distribution. `key_id` identifies a key by a truncated digest; it is not a trust anchor.

## Options considered

1. **Keep one host key and restrict access** — current behavior, smallest operational surface. Old evidence
   becomes unverifiable if the key is lost; a compromised key compromises authenticity for its lifetime.
2. **Versioned host keyring with explicit rotation/revocation** — preserves old verification but adds key
   custody, retention and compromised-key policy. It still does not give independent public verification.
3. **Asymmetric signatures for a stated third-party audit need** — a public verifier can check without
   receiving signing authority, but key lifecycle and distribution still need design and tests. No custom
   cryptography or silent algorithm migration is acceptable.
4. **Use only digest verification** — checks internal consistency, not issuer authenticity.

## Decision needed

Keep the implemented HMAC contract and label it precisely. Do not hand the host key to an external auditor.
Before accepting a lifecycle change, record who verifies, how long records must remain verifiable, how a
compromised key is revoked, how historic sidecars identify the correct key, and whether a real design partner
requires independent verification. If that requirement exists, propose a separate versioned signature contract
using a maintained library and cross-version test vectors. Do not advertise it before implementation.

## Consequences

Today, `authenticity=valid` means a file matches a host-held shared key; `authenticity=not_checked` means the
key was not supplied. Opt-in signing and unsigned legacy records remain distinguishable. There is no public
authenticity claim, rotation procedure or third-party non-repudiation. A copied key or a same-user process that
can read it can forge evidence; deny-only gates reduce observed agent access but are not OS isolation.

## Validation available now

`hooks/test-evidence-signing.sh` covers key creation, valid/invalid/unsigned sidecars and tampering;
`hooks/test-adf-cli.sh` covers `adf verify`. No rotation, revocation or independent verifier test exists.

## Rollback

Documentation only. Any future scheme must continue to verify existing HMAC sidecars with an explicitly
provided old key and preserve `not_checked` for verification without a key.
