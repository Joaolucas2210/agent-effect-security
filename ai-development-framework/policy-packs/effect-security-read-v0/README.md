# Policy pack `effect-security-read-v0`

**English** · [Português (Brasil)](README.pt-BR.md)

This builder creates an **exact, session-bound host read policy** for the existing PDP and PEP ([ADR 0011](../../docs/architecture-decision-records/0011-pinned-host-read-policy.md)). It adds no effect or execution engine. The runtime still applies the versioned [sensitive-path policy v2](../../runtime/v1/policies/sensitive-path-policy-v2.json) at the read. ADF only decides requests seen at [installed edges](../../../docs/product/BOUNDARY.md#support-matrix).

## What it checks

`adf policy build` takes `--run-id`, one or more exact `--allow` paths and an output file. It refuses paths covered by the runtime policy or pack extras in [`pack.json`](pack.json), then reloads the generated policy before printing its pin. Wildcards and a free-form policy DSL are not supported. A denied path can still be denied by the PDP (`invalid_scope` or `scope_not_allowlisted`) before the runtime. Neither the pack nor a successful local trial proves that a host has installed and reviewed this policy.

## Build and pin for a real session

After [local installation](../../../docs/product/QUICKSTART.md), from the ADF clone:

```bash
adf policy build --run-id '<client-session-id>' --allow README.md --out /absolute/host-policy.json
# prints: export ADF_READ_POLICY_FILE=/absolute/host-policy.json ADF_READ_POLICY_SHA256=<pin>
```

The host must set `ADF_READ_POLICY_FILE` and `ADF_READ_POLICY_SHA256` in the hook environment for that session, review the file and retain the printed SHA-256 pin. The policy's `run_id` must match the client's session ID. Keep the pin fixed within a session; review any new allowlist between sessions. Without a configured policy, the reference demo can synthesize a grant for the requested path; do not treat that as a reviewed host allowlist. A missing, incomplete or wrong configured pin yields `host_policy_invalid`, never a fallback to demo mode. [Host activation and trials](../../docs/trials.md#many-projects-one-hook-req-mp-01).

## Per-principal paths

```bash
adf policy build --run-id '<client-session-id>' --allow README.md --allow src/app.py \
  --principal claude:main=README.md \
  --principal claude:backend-reviewer=src/app.py \
  --out /absolute/host-policy.json
```

Naming any principal closes the policy to unnamed principals. A named principal receives only its listed paths, inside the top-level `--allow` ceiling; `--max-act-depth` can further cap a principal's delegation depth ([ADRs 0024](../../docs/architecture-decision-records/0024-principal-rules-in-pinned-policy.md), [0033](../../docs/architecture-decision-records/0033-subagent-principal-propagation.md)). The local hook asserts `claude:<agent_type>` from the client payload; it is not OS identity.

## Expected reasons and limits

| Request | Expected reason | Stage / record |
| --- | --- | --- |
| Allowlisted `README.md` | `read_delivered` | Composed read; bundle |
| Root or nested `.env` | `invalid_scope` | PDP deny; bundle since ADR 0036 |
| Valid path outside the allowlist | `scope_not_allowlisted` | PDP deny; bundle |
| Hand-edited policy with wrong pin | `host_policy_invalid` | Adapter reject; attempt journal, no fallback |
| Invalid traversal (`..`) | `invalid_referenced_contract` | Contract reject; attempt journal, no bundle |
| Unlisted principal | `principal_not_allowlisted` | PDP deny; bundle |

An admitted path can still be denied by the runtime with `sensitive_path_denied`. The bundle's `delivery_mode` matters: `gate_only` on a native tool does not prove its delivered bytes; `mediated` returns controlled snapshot bytes. See the [evidence boundary](../../../docs/product/BOUNDARY.md#evidence-is-the-record-telemetry-only-visualizes). The pack does not intercept scripts, arbitrary Bash or processes outside the installed edge. Test: `bash ai-development-framework/hooks/test-policy-pack.sh`.
