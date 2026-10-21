# ADR 0013: borda A2A — AuthN no transporte, AuthZ por skill antes do PDP

> **English summary.** The A2A protocol defines how an agent announces required authentication but not who may do what, and an A2A edge must feed the existing PDP -> PEP -> Runtime -> Evidence chain without bypassing it. The decision makes `integration/a2a_gateway.py` a loopback-only transport and identity adapter, never a source of authorization: bearer credentials only in the header (otherwise `credential_in_payload`), a closed JSON-RPC schema, and a fixed fail-closed order of payload, AuthN, known skill, scope (`SKILL_SCOPES`), pinned host policy and PDP, with the Agent Card used only for discovery and `admit_read` returning `effect: "not_executed"` in A2A-2. Status: Accepted, human acceptance on 2026-10-14 (A2A-1/2 in main, #55). Residual risks: a stolen token is valid until `exp` with no sender binding, HS256 is a symmetric pilot-only secret, the gateway is not a sandbox, and it has no TLS of its own. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-14 (A2A-1/2 em main, #55).
- **Date:** 2026-10-14
- **Depends on:** ADRs 0007–0009, 0011.
- **Scope:** A2A-0 (esta ADR), A2A-1 (Agent Card fechado), A2A-2 (bearer + scopes + PDP).

## Problema

O protocolo A2A padroniza como um agente **anuncia** a autenticação exigida
(`securitySchemes` no Agent Card), mas não define **quem pode fazer o quê**.
Essa decisão é do agente receptor. No ADF, a autoridade já existe e não muda:
PDP → PEP → Runtime → Evidence. Uma borda A2A precisa alimentar essa cadeia sem
contorná-la, do mesmo modo que os gates Claude `PreToolUse` e Codex `Bash`.

## Decisão proposta

Uma borda A2A local (`integration/a2a_gateway.py`) é um **adaptador de
transporte e identidade**, nunca uma fonte de autorização:

```text
cliente A2A → HTTP + Authorization: Bearer (nunca no corpo JSON-RPC)
  → gateway: rejeita credencial no payload → valida token → scope da skill
  → skill → ToolCallIntent (schema fechado, policy do host pinada)
  → PDP.decide()  (fail-closed)
  → [A2A-3] PEP/Runtime só para classes de efeito já admitidas (leitura confinada)
  → [A2A-3] Evidence (sub, cadeia act, skill, outcome) — auditoria, não permissão
```

### As cinco camadas mapeadas

| Camada | Onde vive | Estado nesta ADR |
| --- | --- | --- |
| 1. AuthN (transporte) | header `Authorization: Bearer`; validador com `iss`, `aud`, `exp`, assinatura | A2A-2: HS256 stdlib como IdP de teste; produção (OIDC/JWKS, mTLS) é config, PR futura |
| 2. AuthZ por skill (scopes) | `SKILL_SCOPES` no gateway → depois PDP com policy pinada do host | A2A-2: skill desconhecida/scope ausente nega antes do PDP; scope presente não admite sozinho |
| 3. Cadeia de delegação | claim `act` (RFC 8693) registrada; `aud` restrito a este agente impede passthrough | A2A-2 só registra `act`; broker de Token Exchange é ADR própria (A2A-4) |
| 4. `auth-required` no meio da tarefa | mapeia para outcome sem efeito (`approval_required`/deny); retomar exige nova admissão | A2A-5, não implementado |
| 5. `input-required` para ação sensível | confirmação humana antes do efeito | A2A-5; nenhuma skill irreversível existe |

### Regras normativas

- Agent Card, `securitySchemes` e `security` por skill são **descoberta**. Nenhum
  código lê o card para decidir; a decisão usa `SKILL_SCOPES` + PDP.
- Credencial só no header. Corpo com chave sensível ou valor com forma de JWT/Bearer
  é negado (`credential_in_payload`) antes da AuthN. O request JSON-RPC é um schema
  fechado (`additionalProperties: false`): `decision_id`, bundle ou grant no corpo são
  rejeitados — decisão anterior não autoriza chamada nova.
- Ordem fixa e fail-closed: payload → AuthN → skill conhecida → scope → policy do host
  configurada → PDP. Qualquer falha nega com `reason_code` estável; nenhum erro cru,
  token ou claim bruta sai na resposta ou no log.
- Regra de domínio além do scope (“só paths aprovados”) é a policy pinada do host
  (ADR 0011), decidida pelo PDP. Sem policy do host o gateway nega; o modo demo do
  adapter, que sintetiza grants a partir do path, **nunca** é usado aqui.
- `admit_read` em A2A-2 não executa nada (`effect: "not_executed"`). Ligar ao PEP é
  A2A-3. Nenhuma skill de escrita (`peticionar`/`write`) é declarada sem ADR própria.
- Claims (`sub`, `scope`, `act`) ficam **fora** do `ToolCallIntent` v1, que continua fechado e
  compartilhado com os gates Claude/Codex. A identidade vai num envelope paralelo `CallerPrincipal`
  (ADR 0014, fatia A2A-3); caminhos locais seguem sem principal.
- Transporte HTTP só em loopback (`127.0.0.1`/`::1`); o gateway recusa outro bind.
  A ADR 0012 continua stdio-only para MCP; esta ADR abre HTTP apenas para a borda A2A.

## Ameaças e risco residual

- **Token roubado** dentro do `exp` autoriza o mesmo que o dono; sem binding de
  sender (DPoP/mTLS) nesta fase. Mitigação: `exp` curto, `aud` estrito.
- **HS256 é segredo simétrico**: só para piloto/teste; segredo vem do ambiente,
  nunca do repositório. Produção exige assinatura assimétrica (RS256/ES256 + JWKS).
- **Gateway não é sandbox**: não isola host nem processo; contém só o que passa por ele.
  Um agente com outra rota de leitura contorna a borda.
- **Sem TLS próprio**: loopback apenas; exposição de rede exige proxy TLS + ADR.
- **Card não autentica o servidor** para o cliente; card assinado fica fora de escopo.

## Não-objetivos

Orquestrador multiagente, Langflow/LangGraph como fronteira, IdP OAuth completo,
certificação de conformidade A2A, efeitos `write`/`network`, Token Exchange broker.

## Reversão

Remover `integration/a2a_gateway.py`, os dois schemas `a2a-*` e o teste. Nenhum
contrato v1 existente muda; PDP/PEP/Evidence ficam intactos.

## Aceite e validação

Testes negativos primeiro: sem token, assinatura inválida, `alg` diferente, expirado,
`aud`/`iss` errados, scope ausente, skill desconhecida, credencial no corpo, replay de
`decision_id`, PDP nega path fora da policy — nenhum chega ao runtime. Card público
sem skills protegidas; card estendido só autenticado; ambos validam no schema fechado.
Rodar `make quality`, `make eval`, `make eval-required`; gates indisponíveis são skipped.

Fontes: [A2A spec — Authentication & Authorization](https://a2a-protocol.org/latest/specification/),
[RFC 8693 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693),
[RFC 7519 JWT](https://www.rfc-editor.org/rfc/rfc7519), [RFC 8725 JWT BCP](https://www.rfc-editor.org/rfc/rfc8725).
