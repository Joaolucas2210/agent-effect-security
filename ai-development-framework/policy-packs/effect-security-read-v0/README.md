# Policy pack `effect-security-read-v0`

A host read policy focused on secrets, for design partners. It produces the **existing** pinned host
policy from [ADR 0011](../../docs/architecture-decision-records/0011-pinned-host-read-policy.md). There is
no new engine: the PDP, the PEP and the runtime's `sensitive-path-policy-v1` decide exactly as before.

## What it does

`build.py` takes an **exact** allowlist of repo-relative files and a run/session ID. It writes the host
policy JSON, then reloads it through the adapter's own `load_host_policy` before it prints the pin.
It refuses to allowlist any path that matches the runtime denylist or the extras in `pack.json`. The
check ignores case, so `config/.ENV` is refused too.

| Source | Denies (path component) |
| --- | --- |
| Runtime (`runtime/v1/policies/sensitive-path-policy-v1.json`) | `.env`, `.env.*`, `.git`, `secrets`, `credentials`, `id_rsa`, `*.pem`, `*.key` |
| Pack (`pack.json`) | `.ssh`, `.aws`, `.azure`, `.gnupg`, `.kube`, `.docker`, `.netrc`, `.npmrc`, `.pypirc`, `.pgpass`, `id_ed25519`, `id_ecdsa`, `id_dsa`, `secret`, `terraform.tfstate`, `secrets.*`, `credentials.*`, `*.p12`, `*.pfx`, `*.jks`, `*.keystore`, `*.ppk`, `*.tfstate`, `*.tfvars` |

Anything not on the allowlist is denied anyway (`scope_not_allowlisted`). The denylist is there so a
reviewer cannot approve a secret by mistake, and the runtime still denies one that slips through.

## Install on another repo

```bash
make install-metrics DEST=/abs/other-repo     # copies ai-development-framework/, including this pack
cd /abs/other-repo && python3 -m venv .venv-adf && export ADF_CONTRACTS_PYTHON="$PWD/.venv-adf/bin/python3"
make -f Makefile.adf install-dev
git -C /abs/other-repo rev-parse HEAD          # record the SHA you trial against

"$ADF_CONTRACTS_PYTHON" ai-development-framework/policy-packs/effect-security-read-v0/build.py \
  --run-id "<session_id>" --allow README.md --allow docs/architecture.md \
  --out /abs/host-policy.json
# prints: export ADF_READ_POLICY_FILE=/abs/host-policy.json ADF_READ_POLICY_SHA256=<pin>
```

Then put those two variables, plus `ADF_TRUSTED_REPOSITORY` and `ADF_EVIDENCE_DIR`, in the hook's
environment. The hook setup is in [trials.md](../../docs/trials.md#4-habilitar-o-hook-de-leitura).

**Pinning rules:** the policy is bound to the run ID. For Claude Code that is the hook's `session_id`, so
you build one policy per session. Keep the pin fixed during a session, review a new version between
sessions, and commit `pack.json` changes through a reviewed PR. Whoever can change the host's
environment can change the authority; the pin only detects drift.

## Per-principal allowlists (ADR 0024)

```bash
"$ADF_CONTRACTS_PYTHON" ai-development-framework/policy-packs/effect-security-read-v0/build.py \
  --run-id "<session_id>" --allow README.md --allow src/backend/app.py --allow config/settings.yaml \
  --principal claude:backend-reviewer=src/backend/app.py,README.md \
  --principal claude:security-reviewer=config/settings.yaml \
  --out /abs/host-policy.json
```

Any `--principal` closes the policy: a principal that is not named is denied (`principal_not_allowlisted`), a
request without a principal is denied (`principal_required`), and a named principal only gets its own paths
(`scope_not_allowlisted_for_principal`). `--allow` stays the ceiling; a principal path outside it is refused at
build time. Local edges get their principal from the hook payload (`claude:<agent_type>`, ADR 0023); the A2A
edge uses the token's `sub`.

## Reason codes you will see

| Request | Gate result | Layer |
| --- | --- | --- |
| `README.md` (allowlisted) | allow · `read_delivered` | — |
| `.env` (repo root) | deny · `invalid_referenced_contract` | v1 path contract: root dotfiles never validate |
| `config/.env` | deny · `invalid_scope` | PDP: no `.env`/`.git` component |
| `secrets/db.txt` (not allowlisted) | deny · `scope_not_allowlisted` | PDP: pinned allowlist |
| a secret allowlisted by hand-editing the JSON | deny · `sensitive_path_denied` | Runtime |
| wrong or missing pin | deny · `host_policy_invalid` | Adapter; never falls back to the demo |
| path of another principal, unnamed principal, no principal (policy with `--principal`) | deny · `scope_not_allowlisted_for_principal`, `principal_not_allowlisted`, `principal_required` | PDP (ADR 0024) |

Every row with a bundle verifies offline, including `invalid_scope`: before 2026-10-19 that
bundle did not verify, and the A2A edge answered 500 (WP1b in the
[implementation plan](../../../docs/product/IMPLEMENTATION_PLAN.md)).

## Not covered

- Reads that do not go through a gated edge: Claude `Bash`/`Grep`/`Glob`; Codex `head`, `sed`, `rg`,
  `python -c`, pipes; any other process. See the [support matrix](../../../docs/product/BOUNDARY.md#matriz-de-suporte).
- Bugs or permission bypasses in the agent or IDE itself (vendor CVEs).
- Wildcards: the allowlist is exact paths by design (ADR 0011).
- Writes, network and every effect other than `read`.

Test: `bash ai-development-framework/hooks/test-policy-pack.sh`.
