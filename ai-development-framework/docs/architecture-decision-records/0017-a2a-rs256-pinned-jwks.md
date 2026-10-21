# ADR 0017: validação RS256 da borda A2A com JWKS local pinada pelo host

> **English summary.** With HS256 the gateway holds the same secret that signs tokens, so anyone who reads it can issue any `sub`, scope or `act` chain. The decision adds `RS256JwksValidator`, which verifies RS256 against a local JWKS pinned by the host (`ADF_A2A_JWKS_FILE`, `ADF_A2A_JWKS_SHA256`; partial or invalid configuration gives `jwks_invalid` with no fallback), accepts only closed RSA entries (modulus of at least 2048 bits, `e = 65537`, unique `kid`), requires `alg` to be exactly `RS256`, and is implemented in the standard library with a constant-time comparison against the full expected EMSA encoding; without the two variables the pilot keeps HS256. Status: Accepted, human acceptance on 2026-10-16. Residual risk: trust moves to the IdP private key and the pinned JWKS file, a stolen token stays valid until `exp` (capped at `MAX_TOKEN_LIFETIME_SECONDS`, 1 h), and the RSA code is small and tested (negative tests, mutation, `openssl` oracle) but is not an audited library. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-16.
- **Date:** 2026-10-16
- **Depends on:** ADRs 0011, 0013, 0014, 0015 e 0016 (Accepted; esta branch empilha nelas).
- **Scope:** troca do segredo simétrico de piloto por chaves públicas na AuthN A2A. Não é IdP.

## Problema

Com HS256, o gateway guarda o mesmo segredo que assina os tokens. Quem lê esse segredo emite
qualquer `sub`, scope ou cadeia `act` (risco residual das ADRs 0013 e 0015). Um verificador
precisa ter apenas o necessário para verificar.

## Decisão proposta

- `RS256JwksValidator` verifica RSASSA-PKCS1-v1_5/SHA-256 (RFC 7518 §3.3) contra uma JWKS **local**.
  O gateway só tem chaves públicas e não consegue emitir tokens.
- **Pin do host, como na ADR 0011:** `ADF_A2A_JWKS_FILE` (caminho absoluto) e
  `ADF_A2A_JWKS_SHA256` (SHA-256 dos bytes do arquivo). Configuração parcial, pin divergente ou
  conteúdo inválido → `jwks_invalid` no start, sem fallback para HS256. Sem as duas variáveis,
  o piloto HTTP continua usando HS256 (`ADF_A2A_HS256_SECRET`), como antes.
- **JWKS fechada:** cada entrada só pode ter `kty=RSA`, `kid`, `n`, `e`, `alg=RS256` e
  `use=sig`. `n` ≥ 2048 bits, `e = 65537`, `kid` únicos, pelo menos uma chave. Entradas com
  `x5c`, EC ou outros algoritmos são rejeitadas: preferimos falhar fechado a aceitar formatos que
  não testamos.
- **Token:** `alg` precisa ser exatamente `RS256` (isso barra `none` e a confusão HS256 com chave
  pública), e o `kid` precisa existir (`token_key_unknown`). As regras de claims (`iss`, `aud`
  exato, `exp`, `nbf`, `sub`) são as mesmas do piloto, numa base comum.
- **Verificação em stdlib:** `pow(s, e, n)` sobre a assinatura com exatamente `k` bytes e `s < n`
  (RFC 8017 §8.2.2), comparando em tempo constante com a codificação EMSA esperada **inteira**.
  Não há parse do bloco decifrado, então não há oráculo de padding nem aceitação de assinatura
  maleável. Nenhuma dependência nova; um teste usa o `openssl` como oráculo independente quando
  ele está disponível (skip reportado quando falta).
- **Hardening após review de segurança:** o módulo precisa ser ímpar, sem fatores primos < 1000
  e ter ≤ 8192 bits (um `n` degenerado, como `2^2048`, permitiria forjar assinaturas; o teto
  limita a CPU por verificação). Cada segmento é base64url canônico (sem `+`, `/` ou `=`), um
  header com `crit` é recusado (RFC 7515 §4.1.11), e JSON aninhado demais vira `token_malformed`,
  `invalid_request` ou `jwks_invalid`, nunca uma conexão derrubada.
- O `CallerPrincipal.authn_method` ganha `bearer_jwt_rs256` (aditivo), e o record mostra qual
  validador autenticou.
- **Rotação:** várias chaves com `kid` distintos. Para trocar, o host publica um arquivo novo e
  atualiza o pin; não há fetch remoto.

## Fora de escopo

Fetch HTTP de JWKS / OIDC discovery, cache e rotação automática, ES256/EdDSA, mTLS, DPoP, IdP
próprio, endpoint de Token Exchange.

## Risco residual

A confiança passa a estar na integridade da chave privada do IdP e do arquivo JWKS pinado; o pin
detecta troca do arquivo, não comprometimento do IdP. Um token roubado ainda vale até `exp` (sem
binding de sender), limitado a `MAX_TOKEN_LIFETIME_SECONDS` (1 h) à frente na AuthN. A cadeia `act` continua sendo declarada pelo emissor. A implementação RSA é
própria e pequena; ela é coberta por testes negativos, mutação e oráculo `openssl`, mas não é uma
biblioteca auditada. Trocar por uma biblioteca exige uma decisão de dependência.

## Reversão

Remover as variáveis `ADF_A2A_JWKS_*`: o piloto volta ao HS256. Remover `RS256JwksValidator`
não muda nenhum contrato além do valor extra no enum de `authn_method`.
