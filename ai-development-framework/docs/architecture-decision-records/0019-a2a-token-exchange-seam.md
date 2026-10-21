# ADR 0019: Token Exchange (RFC 8693) na borda A2A — seam local, endpoint adiado

> **English summary.** ADR 0015 validates per-hop token exchange on receipt, but it was open whether this gateway should issue derived tokens for a downstream agent. The decision fixes `exchange_hs256(...)` as the single seam and states the normative rules any future issuer must follow: full validation of the subject token, requested scopes a subset of the parent's (otherwise `scope_escalation_denied`), exact next-hop `aud`, the `act` chain appended with cycle and depth checks (`delegation_chain_invalid`), `exp` no later than the parent's, and no bearer passthrough. Status: Accepted, human acceptance on 2026-10-16, with the decision "won't do yet" for an exchange endpoint and RS256 issuance, because issuing would put a private key in the gateway, contrary to ADR 0017, and no design partner has asked for multi-hop. Residual risk: without a trusted external AS the proof of scope reduction is local, `DELEGABLE_SCOPES` on receipt is host policy, and the `act` chain is asserted by the issuer. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-16. Decisão: **won't do yet** para endpoint e emissão RS256.
- **Date:** 2026-10-16
- **Depends on:** ADRs 0013, 0015, 0016, 0017 e 0018.
- **Scope:** A2A-7: fixa as regras da troca de token por hop e o que **não** entra agora.

## Problema

Em A → B → C, gateways de mercado trocam o token a cada hop (`aud` do próximo hop, scopes ⊆,
`act` anexado). A ADR 0015 já valida isso no **recebimento** e tem o test double
`exchange_hs256`. Falta decidir se este gateway passa a **emitir** tokens derivados para C.

## Decisão

1. **Seam = `exchange_hs256(validator, subject_token, actor, requested_scopes, audience, secret, ttl)`.**
   Uma implementação, sem interface `TokenExchanger` (não há segunda implementação para
   abstrair). As regras normativas, que qualquer emissor futuro precisa cumprir:
   - o subject token passa pela validação completa deste hop (assinatura, `iss`, `aud`, `exp`)
     antes de qualquer derivação;
   - `requested_scopes ⊆ scopes do pai`, senão `scope_escalation_denied`;
   - `aud` = próximo hop, exato (nunca multi-audience);
   - `act` = `{sub: actor, act: <cadeia do pai>}`; ciclo ou profundidade > `MAX_ACT_DEPTH` →
     `delegation_chain_invalid`, antes de assinar;
   - `exp ≤ exp do pai`;
   - o bearer do usuário nunca é repassado: o corpo continua fechado (`credential_in_payload`) e
     o gateway não faz chamadas de saída.
2. **Won't do yet:** endpoint de exchange (mesmo opt-in) e emissão RS256. Emitir exige uma chave
   privada no gateway e o transforma em emissor/AS — uma fronteira de confiança nova, contrária
   à ADR 0017 (o gateway só guarda chaves públicas). Nenhum design partner pediu multi-hop até
   aqui; sem esse consumidor, o endpoint seria superfície sem uso.
3. **Revisitar quando:** um design partner precisar de C real atrás deste gateway, **ou** houver
   um AS externo confiável (que então emite, e este gateway só valida — preferido). Essa decisão
   pede ADR própria com gestão de chave privada, rotação e chamada de saída.

## Fora de escopo

IdP de produção, rotação automática de JWKS, federação multi-org, chamadas de saída.

## Risco residual

O emissor deve ser confiável: sem AS externo, a prova de redução de scopes é local (test
double) e, no recebimento, o teto `DELEGABLE_SCOPES` é policy do host, não prova criptográfica.
A cadeia `act` é afirmada pelo emissor. Token derivado roubado vale até `exp` (≤ pai, ≤ 1 h).

## Reversão

Nada a reverter: nenhuma superfície nova. Um endpoint futuro substitui o "won't do yet" por ADR.
