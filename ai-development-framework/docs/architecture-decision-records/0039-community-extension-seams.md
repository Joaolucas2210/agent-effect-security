# ADR 0039: Community extension seams for the read adapter

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** maintainer (pending).
- **Depends on:** ADRs 0023, 0026, 0029, 0030 (Accepted); relates to ADR 0038 (Proposed) and ADR 0040 (typed host config).

## Context

`LocalReadAdapter` builds every collaborator itself: the host policy (`load_host_policy`), bundle persistence
(`persist_bundle`), signing (`sign_if_configured`, called from persistence and from `AttemptJournal`), the attempt
journal, the workspace manager, runtime and PEP. The caller principal is already a per-call argument. The Phase 1
open-core audit (ARCH-08, ARCH-12, §6) asks for composition seams so that other distributions can plug in around the
Community decision core without forking or monkey-patching it. Its §6 principle is the constraint: no seam may widen a
Community decision, skip PEP revalidation, or make evidence optional.

The framework rule is "no interface with one implementation". A seam is therefore justified only by a second consumer
today or by a deliberate, documented extension point, and each must ship with the current behaviour as its default.

## Options considered

1. **Cut all four candidate seams** (`PolicySource`, `EvidenceSink`, `Signer`, `IdentityResolver`). Pros: matches the
   Phase 1 list. Cons: three of them would have one implementation each. `EvidenceSink` and `Signer` would cover only
   the bundle, while the journal and the A2A record keep signing through the module function, so the evidence on
   disk would be split across two mechanisms. A replaceable sink also makes the mandatory local write optional.
2. **Cut only `PolicySource`** with the file + pin as default, re-validated by the adapter whatever the source
   returns. Pros: there is a second consumer today (the A2A gateway loads the same pinned policy for its own principal
   rules and the adapter loads it again), and it is the seam Phase 1 marks as missing for central policy distribution.
   Cons: one more constructor argument.
3. **Do nothing.** Pros: zero code. Cons: ARCH-08 stays open, and the first external policy distributor would patch
   `load_host_policy`.

## Decision

Option 2.

- `integration/extensions.py` defines `PolicySource` (`typing.Protocol`: `load() -> (config, sha256_pin) | None`) and
  the default `HostPolicyFile(path, sha256)`. `None` selects the reference demo exactly as "both variables absent"
  does today.
- `LocalReadAdapter(..., policy_source=None)`: `None` builds `HostPolicyFile(host_policy_path, host_policy_sha256)`,
  so every existing caller is unchanged. The source is consulted once, in the constructor, as today.
- Every source result goes through `check_host_policy` (the validation `load_host_policy` always did: shape, schema
  version, pin, contract schemas, inner digests) on a deep copy. A source that raises, returns anything else, or is
  passed together with the legacy pair makes every read deny with `host_policy_invalid` before a workspace exists.
- Selection is an explicit constructor argument. There is no registry, entry point, dynamic import or environment
  variable that picks a source.

Rejected seams:

- **`EvidenceSink`**: no second implementation exists. The local, owner-only, exclusive write followed by signing is
  the evidence guarantee (ADR 0030) and must happen before delivery. A remote or WORM store can read the evidence
  directory out of process, which `evidence_dir` already allows. If an in-process remote sink is ever needed, it must
  be an additional writer after the local write, with its own ADR.
- **`Signer`**: HMAC is the only algorithm, and it is called from three places (bundle, journal, A2A record). A seam
  in the adapter alone would split them. Asymmetric signing is ADR 0038's decision. The second algorithm brings the
  seam, together with a sidecar format change, in its own ADR.
- **`IdentityResolver` / `PrincipalProvider`**: the seam already exists. `read(..., principal=)` takes the principal
  from the edge (hooks use `local_principal`, A2A uses validated JWT claims), and the PDP and PEP check it against the
  caller-principal contract. A resolver inside the adapter would duplicate it.

## Invariants (tested in `hooks/test-extension-contracts.{py,sh}`)

1. The PDP decides and the PEP revalidates every read, whatever the source. A source only supplies pinned input to
   the request.
2. A source cannot bypass the pin, the schemas or the inner digests, and cannot mutate the policy after the check.
3. The sensitive-path and root-dotfile rules still deny under any grant from a source.
4. The R-09 `gate_only` live-path check runs before any workspace or decision.
5. Persistence and signing failures keep their deny codes (`adapter_failed`, `evidence_signing_unavailable`). No
   seam can mark unsigned evidence as signed.
6. Default wiring is equivalent to the code before this ADR: outcome, reason code, content, bundle structure and
   stable fields, and file layout/permissions.

## Not allowed through any seam

- Weakening a Community decision, skipping PDP or PEP, or making local evidence optional.
- Private or proprietary evidence, policy or signature formats; seams carry the public contracts unchanged.
- Changing crypto, key handling, policy evaluation or hook contracts. Each of these needs its own ADR.

## Consequences

- Positive: ARCH-08 closed for policy; the A2A gateway can share one pinned policy object (follow-up, optional).
  Equivalence is enforced by tests, not by review.
- Negative / debt: `ponytail:` `EvidenceSink`, `Signer` and a narrowing-only `Decider` stay out until a second
  implementation exists. The source is host code and is trusted to name its pin. Who may supply a source is the host's
  decision, outside this ADR.
- Reversibility: cheap. Removing the parameter restores the previous constructor. `load_host_policy` keeps its
  signature and errors.

## Metrics impact

One new module (~35 lines) with one Protocol and one class. One optional constructor parameter. `load_host_policy`
is split into read + `check_host_policy`. No new dependency, schema, reason code or exit code.

## Phase 2C evidence (2026-11-09, appended; status unchanged)

- The second consumer is now wired: `A2AGateway(..., policy_source=None)` builds one source (default
  `HostPolicyFile(path, pin)`), checks it with `check_host_policy` on a deep copy, and hands the checked policy to the
  adapter through an in-memory source, which re-checks its own copy. The policy file is read once instead of twice.
- At the edge, `None` (the demo selector) is refused with 503 `host_policy_invalid`; the A2A path never serves the
  reference demo. A source plus the path/pin pair is ambiguous and refused, as in the adapter.
- Evidence: `hooks/test-a2a-policy-source.{py,sh}` (12 tests, 16 off-contract source cases); the existing 52 gateway
  tests pass unchanged; a 120-case old-vs-new differential (10 host configurations × 12 requests) showed 0
  differences in status, JSON-RPC body, A2A record and evidence layout. Mutants that drop the gateway check, the
  ambiguity guard, the deep copy or the single load are each killed by a test.
- One intentional delta: before, a policy file that became unreadable between the gateway's load and the adapter's
  second load made reads deny with `host_policy_invalid` (HTTP 200). Now the single checked policy is used. The
  content is the same pinned, checked policy either way.
- Report: `docs/audits/open-core-phase-2c/03-a2a-public-contracts.md`.
