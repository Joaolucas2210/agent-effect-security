# ADR 0015: delegação A2A — cadeia `act` validada, scopes monotônicos, sem passthrough

> **English summary.** In a chain A -> B -> C the risks are token passthrough and scopes accumulating across hops, and ADR 0013 only recorded `act`. The decision forbids passthrough (closed body, exact `aud`, no outbound calls), validates the `act` chain (closed levels, depth ≤ 8, no repeated `sub`, otherwise 401 `delegation_chain_invalid`), and enforces monotonic scopes: the `exchange_hs256` test double requires the requested scopes to be a subset of the parent's, and a received delegated token may carry only scopes within the host ceiling `DELEGABLE_SCOPES` (currently `workspace:read`), otherwise 403 `scope_escalation_denied`. Status: Accepted, human acceptance on 2026-10-16 (record dated 2026-10-14). Residual risk: the receiving ceiling is host policy, not cryptographic proof that the issuer reduced scopes, the `act` chain is asserted by the issuer rather than verified hop by hop, and with HS256 whoever holds the secret can issue any chain. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-16.
- **Date:** 2026-10-14
- **Depends on:** ADRs 0013 e 0014 (Accepted).
- **Scope:** A2A-4: semântica de delegação na borda A2A. Não é um Authorization Server.

## Problema

Na cadeia A → B (este gateway) → C, o risco clássico é B repassar o token do usuário para C
(passthrough) ou C aceitar um token que acumulou scopes ao longo dos hops. A 0013 só
registrava `act`; faltava regra explícita para forma, ciclos e escalada de scope.

## Decisão proposta

1. **Sem passthrough.** O corpo JSON-RPC continua fechado (ADR 0013): um campo
   `downstream_token`, `subject_token` ou `actor_token` é rejeitado (`credential_in_payload` /
   `invalid_request`). O gateway não faz chamadas de saída. `aud` continua exato: um token
   emitido para outro agente, ou para a API ampla do usuário, falha na AuthN (401
   `token_audience_invalid`). O token de cada hop precisa ser emitido para o `aud` deste gateway.
2. **Cadeia `act` validada** (RFC 8693 §4.1; o `act` mais externo é o ator atual). Cada nível é
   fechado (`{sub, act?}`), `sub` segue o padrão de subject, a profundidade é ≤ 8, e nenhum
   `sub` se repete em `[sub, act…]` (sem ciclos, nem o sujeito agindo por si). Qualquer falha
   dá 401 `delegation_chain_invalid`, antes de PDP e evidência. A cadeia válida vai para
   `CallerPrincipal.act` e para o `A2AEvidenceRecord` (resumo redigido: só os `sub`).
3. **Scopes monotônicos.**
   - **Na derivação:** o test double `exchange_hs256` (estilo RFC 8693, só para testes e piloto
     local, sem endpoint público) exige `requested ⊆ scopes do token pai`; caso contrário,
     `scope_escalation_denied`. Ele também força `exp ≤ exp do pai`, fixa `aud` no próximo hop
     e anexa o ator atual ao `act`.
   - **No recebimento:** este gateway não vê o token pai. Por isso um token delegado (`act` não
     vazio) só pode carregar scopes do teto de delegação do host (`DELEGABLE_SCOPES`, hoje
     `workspace:read`). Qualquer scope acima disso faz a request inteira cair com 403
     `scope_escalation_denied`, gravado como evidência, em vez de ser ignorado em silêncio.
   - Ter scope continua sem admitir nada: PDP e PEP decidem como antes.
4. **Validador substituível.** O gateway depende só de `validate(token) -> claims`. HS256
   continua sendo piloto; trocar por JWKS ou mTLS não reescreve o gateway.

## Fora de escopo

Authorization Server e endpoint de Token Exchange reais, JWKS em produção, chamadas de saída
para C, `auth-required`/`input-required` (A2A-5), novas skills, identidade no `ToolCallIntent`.

## Risco residual

O teto de delegação no recebimento é uma policy do host, não uma prova criptográfica de que o
emissor reduziu os scopes. Isso só existe com um AS confiável (follow-up). Um token roubado vale
até `exp`, inclusive um derivado. A cadeia `act` é afirmada pelo emissor, não verificada hop a
hop. HS256 é segredo compartilhado: quem o tem emite qualquer cadeia. A borda não é sandbox.

## Reversão

Remover a validação extra em `act_chain`, o teto `DELEGABLE_SCOPES` e `exchange_hs256`; a cadeia
volta a ser só registrada (comportamento da 0013). Nenhum contrato muda.
