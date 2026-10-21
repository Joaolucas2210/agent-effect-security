# Runbook: A2A edge with RS256/JWKS (enterprise pilot)

**English** · [Português (Brasil)](a2a-rs256-jwks.pt-BR.md)

Audience: the platform team of a design partner that wants to connect the A2A edge to the company IdP
instead of the pilot HS256 secret. Source decision: [ADR 0017](../architecture-decision-records/0017-a2a-rs256-pinned-jwks.md).
The gateway holds only **public** keys, pinned by SHA-256: it verifies tokens, but it cannot issue them.

## 0. Dry run without an IdP (5 minutes)

```bash
make install-dev
make a2a-live-trial AUTH=rs256
```

The runner acts as a test IdP: `openssl` generates the RSA-2048 key and signs the tokens, and the gateway sees
only the pinned public JWKS. The full matrix (401/403/deny/allow/human confirmation) runs on RS256, and
`summary.json` comes out with `auth_mode: rs256_jwks_openssl_test_idp`. This proves the verification path; it does
not prove your IdP configuration. Without `openssl`, the command exits with code 2 and `skipped`, never green.

## 1. IdP token requirements

| Claim / header | Gateway requirement | reason_code on failure |
| --- | --- | --- |
| `alg` | Exactly `RS256`; `crit` is not accepted | `token_alg_rejected` |
| `kid` | Present in the pinned JWKS | `token_key_unknown` |
| `iss` | Equal to `ADF_A2A_ISSUER` | `token_issuer_invalid` |
| `aud` | **String** equal to `ADF_A2A_AUDIENCE`. An array, even with one item, is rejected | `token_audience_invalid` |
| `sub` | `[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}` | `token_claims_invalid` |
| `exp` | Integer, in the future, at most **1 h** ahead | `token_expired`, `token_lifetime_exceeded` |
| `nbf` | Optional; if present, an integer and already valid | `token_not_yet_valid` |
| `scope` | Space-separated **string** containing `workspace:read`. An `scp` array does not count | 403 `insufficient_scope` |

In the IdP, configure a client or audience dedicated to ADF (for example `adf-a2a-<team>`), with a lifetime
of at most 1 h and a `workspace:read` scope. Issue `human:confirm` only for human sessions,
never for machine clients (ADR 0018).

## 2. Export and reduce the JWKS

The loader accepts only `kty`, `kid`, `n`, `e`, `alg` (RS256) and `use` (sig), RSA ≥ 2048 bits and `e = 65537`.
IdP JWKS files usually carry `x5c`/`x5t`, so reduce the file. This download is a host action, done
once and reviewed: the gateway never fetches the JWKS on its own.

```bash
curl -fsS https://<idp>/.well-known/jwks.json -o /tmp/jwks-raw.json
python3 - /tmp/jwks-raw.json /etc/adf/jwks.json <<'PY'
import json, sys
keys = [{k: key[k] for k in ("kty", "kid", "n", "e", "alg", "use") if k in key}
        for key in json.load(open(sys.argv[1]))["keys"] if key.get("kty") == "RSA" and key.get("use", "sig") == "sig" and key.get("alg", "RS256") == "RS256"]
json.dump({"keys": keys}, open(sys.argv[2], "w"), indent=1)
print(len(keys), "key(s):", [key["kid"] for key in keys])
PY
sha256sum /etc/adf/jwks.json        # this is the pin; record it in the change PR/ticket
```

## 3. Start the edge

```bash
"$ADF_CONTRACTS_PYTHON" ai-development-framework/policy-packs/effect-security-read-v0/build.py \
  --run-id a2a-pilot --allow README.md --out /etc/adf/host-policy.json   # prints the policy exports
export ADF_READ_POLICY_FILE=/etc/adf/host-policy.json ADF_READ_POLICY_SHA256=<policy pin>
export ADF_A2A_JWKS_FILE=/etc/adf/jwks.json ADF_A2A_JWKS_SHA256=<JWKS pin>
export ADF_A2A_ISSUER=https://<idp>/ ADF_A2A_AUDIENCE=adf-a2a-<team>
export ADF_TRUSTED_REPOSITORY=/abs/repo ADF_EVIDENCE_DIR=/abs/evidence
unset ADF_A2A_HS256_SECRET          # with a JWKS configured, HS256 is never accepted
cd ai-development-framework && python3 -m integration.a2a_gateway serve
```

A partial configuration, or one with a wrong pin, makes the gateway reject every token (`jwks_invalid`). It does
not fall back to HS256. To expose it beyond the machine, use the TLS proxy from
[CONTROL_PLANE § Transport](../CONTROL_PLANE.md#a2a-edge-a2a-1-to-6). The process listens only on `127.0.0.1`.

## 4. Smoke test with a real token

```bash
TOKEN=<IdP access token for the ADF client>
send() { curl -s -o /dev/stderr -w '%{http_code}\n' -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $1" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"message/send\",\"params\":{\"message\":{\"kind\":\"message\",\"role\":\"user\",\"messageId\":\"m1\",\"parts\":[{\"kind\":\"data\",\"data\":{\"skill\":\"read_workspace_file\",\"arguments\":{\"path\":\"$2\"}}}]}}}"; }
send "" README.md                # expected 401 auth_missing
send "${TOKEN%.*}.AAAA" README.md  # swapped signature: 401 token_signature_invalid
send "$TOKEN" README.md          # 200 outcome=delivered
send "$TOKEN" secrets/db.txt     # 200 outcome=deny scope_not_allowlisted
```

Check the evidence: each request that passed AuthN produced `evidence/_a2a/<record_id>.json` with
`principal.authn_method = "bearer_jwt_rs256"`. Verify it with `verify_record`
([LANGFUSE.md § 3](../observability/LANGFUSE.md#3-correlation-span--evidence--verification)). Do not store the
real token in a file or in an issue.

## 5. Key rotation

1. The IdP publishes the new key alongside the old one.
2. Redo step 2 (both `kid`s), record the new pin and restart the gateway **between sessions**.
3. After the IdP stops signing with the old key, redo step 2 without it and re-pin.

There is no automatic fetch or rotation (ADR 0017). A key outside the pinned JWKS becomes `token_key_unknown`.

## Residual

- The token is a bearer token: without DPoP/mTLS (WP7), a stolen token is valid until `exp` (≤ 1 h).
- The edge proves what the token says, not who requested it; real MFA and human confirmation belong to the IdP.
- RSA verification is in-house stdlib code, tested with mutation and an `openssl` oracle, but it is not an audited library.
- Tasks live in memory: a restart loses `auth-required`/`input-required` pauses (`task_not_found`).
