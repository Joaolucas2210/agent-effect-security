# ADR 0024: `principal_rules` na policy pinada do host

> **English summary.** The pinned host policy (ADR 0011) is a per-host allowlist, so every principal with `workspace:read` can read the same paths and per-agent least privilege did not exist for the PDP. The proposal adds optional `principal_rules` (`{sub, allowed_scopes}` with exact scopes, no wildcard or DSL, covered by `policy_sha256`) to `PolicyBundle` 1.0; when present the policy is closed, yielding `principal_required`, `principal_not_allowlisted` or `scope_not_allowlisted_for_principal`, a principal list can only narrow the host allowlist, and a policy without `principal_rules` decides exactly as before. Status: Accepted by the maintainer on 2026-10-21 (release 0.1.0 preparation), together with ADR 0023, without which local edges are denied with `principal_required` whenever `principal_rules` is set. Residual risk: the policy is only as strong as the asserted identity (the harness for local edges, the token issuer for A2A), and exact per-file scopes do not scale to large repositories without a policy generator. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-21 (mantenedor, preparação do release 0.1.0); antes: Proposed — aguarda aceite humano.
- **Date:** 2026-10-21
- **Depends on:** ADRs 0007, 0011, 0014 (Accepted) e 0023 (Accepted em 2026-10-21; sem ela só a borda A2A teria principal).
- **Scope:** PDP e pack `effect-security-read-v0`. Efeito `read` apenas. Sem IdP, sem orquestração.

## Problema

A policy pinada (ADR 0011) é uma allowlist por host: todo principal que chega com `workspace:read`
pode ler os mesmos paths. No piloto, três subagentes tinham exatamente a mesma autoridade, e vários
tokens A2A com o mesmo scope eram indistinguíveis. "Least privilege por agente" não existia para o
PDP, só na narrativa. Os papers e o mercado pedem o contrário: hierarquia de principals com
privilégio medido (concedido versus exercido).

## Decisão

- `PolicyBundle` 1.0 ganha `principal_rules` opcional: lista de `{sub, allowed_scopes}` com scopes
  exatos, sem wildcard nem DSL (ADR 0011). O `policy_sha256` cobre o campo; editar um principal
  invalida o pin.
- PDP, depois de todas as regras de host (`scope_not_allowlisted` inclusive): se a policy tem
  `principal_rules`, **ela é fechada**. Sem principal → `principal_required`. `sub` ausente da lista
  → `principal_not_allowlisted`. Scope fora da lista do principal → `scope_not_allowlisted_for_principal`.
  Admitido → `applied_rule_ids` ganha `principal:<sub>`. A lista do principal só pode estreitar a do
  host: um path fora da allowlist do host continua `scope_not_allowlisted` mesmo que o principal o liste.
- Policy sem `principal_rules` decide exatamente como antes, com ou sem principal.
- `build.py` do pack aceita `--principal SUB=PATH[,PATH]`, repetível; recusa path fora de `--allow`,
  path sensível, `sub` malformado ou lista vazia, e não imprime pin para o que não carrega.
- Bordas: A2A usa o `sub` do JWT; bordas locais usam o principal da ADR 0023 (`claude:<agent_type>`).
  Com `principal_rules` e sem ADR 0023, as bordas locais são negadas (`principal_required`): fechado
  por desenho, documentado.

## Contratos

Aditivos: `principal_rules` opcional no `PolicyBundle`; três reason codes novos no enum do
`AdapterAttemptEvent`. `AdmissionDecision`, `EvidenceBundle` e `ToolCallIntent` inalterados; o bundle
continua sem principal (o record A2A e o journal dizem quem).

## Risco residual

O `sub` local é afirmado pelo harness (ADR 0023) e o `sub` A2A pelo emissor do token; a policy por
principal vale o que vale a identidade. Scopes exatos por arquivo não escalam para repositórios
grandes sem um gerador de policy; `**` continua proibido, por isso a lista nasce do pack, não da mão.
A medição concedido versus exercido é agregação posterior, fora desta ADR.

## Reversão

Remover `principal_rules` da policy (novo pin) volta ao comportamento da ADR 0011. Remover o bloco do
PDP e o campo do schema é um revert limpo; policies antigas continuam válidas.
