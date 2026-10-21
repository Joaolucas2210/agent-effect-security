# Runbook: borda A2A com RS256/JWKS (piloto enterprise)

[English](a2a-rs256-jwks.md) · **Português (Brasil)**

Para quem: o time de plataforma de um design partner que quer ligar a borda A2A ao IdP da empresa
em vez do segredo HS256 de piloto. Decisão de origem: [ADR 0017](../architecture-decision-records/0017-a2a-rs256-pinned-jwks.md).
O gateway guarda só chaves **públicas** pinadas por SHA-256: ele verifica tokens, mas não consegue emiti-los.

## 0. Ensaio sem IdP (5 minutos)

```bash
make install-dev
make a2a-live-trial AUTH=rs256
```

O runner age como um IdP de teste: o `openssl` gera a chave RSA-2048 e assina os tokens, e o gateway vê
só a JWKS pública pinada. A matriz completa (401/403/deny/allow/confirmação humana) roda em RS256, e o
`summary.json` sai com `auth_mode: rs256_jwks_openssl_test_idp`. Isso prova o caminho de verificação; não
prova a configuração do seu IdP. Sem `openssl`, o comando sai com código 2 e `skipped`, nunca verde.

## 1. Requisitos do token do IdP

| Claim / header | Exigência do gateway | reason_code se falhar |
| --- | --- | --- |
| `alg` | `RS256` exatamente; `crit` não é aceito | `token_alg_rejected` |
| `kid` | Presente na JWKS pinada | `token_key_unknown` |
| `iss` | Igual a `ADF_A2A_ISSUER` | `token_issuer_invalid` |
| `aud` | **String** igual a `ADF_A2A_AUDIENCE`. Um array, mesmo de um item, é recusado | `token_audience_invalid` |
| `sub` | `[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}` | `token_claims_invalid` |
| `exp` | Inteiro, no futuro, no máximo **1 h** à frente | `token_expired`, `token_lifetime_exceeded` |
| `nbf` | Opcional; se presente, inteiro e já válido | `token_not_yet_valid` |
| `scope` | **String** separada por espaço com `workspace:read`. Um array `scp` não conta | 403 `insufficient_scope` |

Configure no IdP um client ou audience dedicado ao ADF (por exemplo `adf-a2a-<time>`), com tempo de vida
de no máximo 1 h e um scope `workspace:read`. `human:confirm` só deve ser emitido para sessões de pessoas,
nunca para clients de máquina (ADR 0018).

## 2. Exportar e reduzir a JWKS

O loader aceita só `kty`, `kid`, `n`, `e`, `alg` (RS256) e `use` (sig), RSA ≥ 2048 bits e `e = 65537`.
JWKS de IdP costumam trazer `x5c`/`x5t`, então reduza o arquivo. Esse download é uma ação do host, feita
uma vez e revisada: o gateway nunca busca a JWKS sozinho.

```bash
curl -fsS https://<idp>/.well-known/jwks.json -o /tmp/jwks-raw.json
python3 - /tmp/jwks-raw.json /etc/adf/jwks.json <<'PY'
import json, sys
keys = [{k: key[k] for k in ("kty", "kid", "n", "e", "alg", "use") if k in key}
        for key in json.load(open(sys.argv[1]))["keys"] if key.get("kty") == "RSA" and key.get("use", "sig") == "sig" and key.get("alg", "RS256") == "RS256"]
json.dump({"keys": keys}, open(sys.argv[2], "w"), indent=1)
print(len(keys), "key(s):", [key["kid"] for key in keys])
PY
sha256sum /etc/adf/jwks.json        # este é o pin; registre-o no PR/ticket de mudança
```

## 3. Subir a borda

```bash
"$ADF_CONTRACTS_PYTHON" ai-development-framework/policy-packs/effect-security-read-v0/build.py \
  --run-id a2a-pilot --allow README.md --out /etc/adf/host-policy.json   # imprime os exports da policy
export ADF_READ_POLICY_FILE=/etc/adf/host-policy.json ADF_READ_POLICY_SHA256=<pin da policy>
export ADF_A2A_JWKS_FILE=/etc/adf/jwks.json ADF_A2A_JWKS_SHA256=<pin da JWKS>
export ADF_A2A_ISSUER=https://<idp>/ ADF_A2A_AUDIENCE=adf-a2a-<time>
export ADF_TRUSTED_REPOSITORY=/abs/repo ADF_EVIDENCE_DIR=/abs/evidence
unset ADF_A2A_HS256_SECRET          # com JWKS configurada, HS256 nunca é aceito
cd ai-development-framework && python3 -m integration.a2a_gateway serve
```

Uma configuração parcial ou com pin errado faz o gateway recusar todo token (`jwks_invalid`). Ele não
cai para o HS256. Para expor fora da máquina, use o proxy TLS da
[CONTROL_PLANE § Transporte](../CONTROL_PLANE.pt-BR.md#borda-a2a-a2a-1-a-6). O processo só escuta em `127.0.0.1`.

## 4. Smoke com um token real

```bash
TOKEN=<access token do IdP para o client do ADF>
send() { curl -s -o /dev/stderr -w '%{http_code}\n' -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $1" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"message/send\",\"params\":{\"message\":{\"kind\":\"message\",\"role\":\"user\",\"messageId\":\"m1\",\"parts\":[{\"kind\":\"data\",\"data\":{\"skill\":\"read_workspace_file\",\"arguments\":{\"path\":\"$2\"}}}]}}}"; }
send "" README.md                # esperado 401 auth_missing
send "${TOKEN%.*}.AAAA" README.md  # assinatura trocada: 401 token_signature_invalid
send "$TOKEN" README.md          # 200 outcome=delivered
send "$TOKEN" secrets/db.txt     # 200 outcome=deny scope_not_allowlisted
```

Confira a evidência: cada request que passou da AuthN gerou `evidence/_a2a/<record_id>.json` com
`principal.authn_method = "bearer_jwt_rs256"`. Verifique com `verify_record`
([LANGFUSE.md § 3](../observability/LANGFUSE.pt-BR.md#3-correlação-span--evidência--verificação)). Não guarde o
token real em arquivo nem em issue.

## 5. Rotação de chave

1. O IdP publica a chave nova ao lado da antiga.
2. Refaça o passo 2 (os dois `kid`), registre o novo pin e reinicie o gateway **entre sessões**.
3. Depois que o IdP parar de assinar com a chave antiga, refaça o passo 2 sem ela e repine.

Não há fetch nem rotação automática (ADR 0017). Uma chave fora da JWKS pinada vira `token_key_unknown`.

## Residual

- O token é bearer: sem DPoP/mTLS (WP7), um token roubado vale até `exp` (≤ 1 h).
- A borda prova o que o token diz, não quem o pediu; MFA e confirmação humana reais são do IdP.
- A verificação RSA é stdlib própria, testada com mutação e oráculo `openssl`, mas não é uma biblioteca auditada.
- Tasks ficam em memória: um restart perde pausas `auth-required`/`input-required` (`task_not_found`).
