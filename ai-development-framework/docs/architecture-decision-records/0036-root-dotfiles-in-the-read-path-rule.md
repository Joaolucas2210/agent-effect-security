# ADR 0036: root dotfiles in the v1 read path rule

- **Status:** Proposed — awaits human acceptance. No code before acceptance; the red eval comes first.
- **Date:** 2026-11-04
- **Deciders:** maintainer.
- **Depends on:** ADRs 0007, 0008, 0011 (Accepted); 0026, 0034 (Accepted process).
- **Scope:** the path grammar of a `read` intent (`tools/pdp.py` `_PATH`, `list-files-input.schema.json`) and the
  compensating `sensitive_path_policy_v2`. No new effect, no change to PEP, runtime open, bindings or evidence.
- **Threats:** THR-01; pilot finding 2 ([PILOT-20261104](../../../docs/product/PILOT-20261104.md)).

## Problem

A v1 read intent path must start with `[A-Za-z0-9]`. Any file or directory at the repository root whose name
starts with `.` is rejected **before** the PDP with `invalid_referenced_contract`: no bundle, only a journal
line. That was a deliberate v1 shortcut — it made the root `.env` unreadable without naming it — but on the four
pilot repositories it also denies `.gitignore`, `.gitleaks.toml`, `.editorconfig`, `.dockerignore`, `.github/`,
`.claude/`, `.codex/`, all of which an agent legitimately reads. The deny is both a false positive for benign
files and a *weaker* proof for the secret ones: a contract deny leaves no verifiable bundle (BOUNDARY, reason
code table).

The shortcut also hides a false sense of coverage: `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`,
`.docker/config.json`, `.kube/config` are unreadable today only *because* they start with a dot, not because
any policy names them. Widening the grammar without naming them would expose them.

## Decision (proposed)

1. **Path rule 1.1.** A path component may start with a single `.`, never be `.` or `..`, and must otherwise
   match the v1 character class. Concretely `_PATH` becomes `(?:\.?[A-Za-z0-9][A-Za-z0-9._-]*)(?:/\.?[A-Za-z0-9][A-Za-z0-9._-]*)*\Z`
   and `list-files-input.schema.json` the same, keeping its existing negative look-aheads (`..`, `//`, shell
   metacharacters, NUL). `_normal_scope` keeps rejecting `..`, `.git` and `.env` components with `invalid_scope`.
2. **`sensitive_path_policy_v2`** (new file, v1 kept loadable, per ADR 0034): v1 plus the components
   `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, `.docker`, `.kube`, `.aws`, `.ssh`, `.gnupg`, `.terraform.d`,
   `.vault-token`, `.pgpass`, `.my.cnf`, `.boto`, `.s3cfg`, `.config` (the XDG root, where `gh`, `gcloud` and
   `hub` keep tokens) and the suffix `.tfrc.json`. Runtime, deny gate and policy-pack builder load v2.
   `sensitive-path-policy-v1.schema.json` is reused unchanged (same shape); the normative oracle gains the v2
   required lists.
3. **What becomes readable and provable:** benign root dotfiles are delivered with a bundle; `.env`,
   `.env.*`, `.git/**` are denied by the PDP (`invalid_scope`) or the runtime (`sensitive_path_denied`) **with a
   bundle**, which is the proof the 2026-10-20 pilot's finding 1 asked for.
4. **Evidence first:** a red eval in `docs/evals` and a new `hooks/test-root-dotfiles.sh` covering: each file
   above denied at the right layer with a bundle; `.gitignore` delivered; `..`, `.`, `./x`, `x/.`, `//`,
   `.env.local` in a subdirectory; the Codex `cat` gate and the 1b grammar on the same names; `project-reasons`
   counts moving from `attempts=` to `total=`.

## Options considered

1. **Keep the shortcut, document it** — status quo; rejected: it is a daily false deny and it weakens the proof
   of the most common secret.
2. **Allowlist of benign dotfile names** (`.gitignore`, `.editorconfig`, …) — fails closed but grows forever and
   still proves nothing for `.env`; rejected.
3. **Widen without a v2 denylist** — exposes the token files listed above; rejected on default-deny grounds.
4. **Proposed: widen + v2 denylist + bundle for every deny.**

## Consequences

- Positive: benign dotfiles readable in enabled projects; `.env` denies become verifiable bundles; the
  denylist states what it protects instead of relying on an accident of grammar.
- Negative: `invalid_referenced_contract` counts drop and `invalid_scope`/`sensitive_path_denied` rise —
  pinned suite metrics change once (document as in WP1b, do not compare series); `tools/v1` schema pattern
  changes inside the 1.0 contract — the intent `schema_version` stays `1.0` because every previously valid
  intent remains valid (widening only), which the contract test must assert explicitly.
- Reversibility: cheap (restore the pattern; v2 file stays).

## Residual risks

A token file at an unlisted dotfile name is readable after this change — exactly the class ADR 0034 exists for;
the v2 list is a snapshot of common CLIs, not completeness. Reads of `.claude/`, `.codex/`, `.github/workflows`
stay allowed (content is tainted; writes are denied by ADR 0028). The Codex `cat` grammar already accepted a
leading dot; after this ADR its denies also carry a bundle.

## Rollback

Restore `_PATH` and the schema pattern; point loaders back to v1. Bundles written meanwhile remain valid.
