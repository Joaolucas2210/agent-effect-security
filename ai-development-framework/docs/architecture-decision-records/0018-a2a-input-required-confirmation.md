# ADR 0018: A2A `input-required` — confirmação humana antes do efeito

> **English summary.** ADR 0016 left `input-required` as a rule only, and a future write skill should not be the first to exercise the pause. The decision implements the mechanism behind a host flag (`confirm_skills` / `ADF_A2A_CONFIRM_SKILLS`, empty by default) on the existing read skill: a flagged request pauses before PDP, PEP and runtime with `reason_code: input_required`, and confirmation requires a resend with the same `taskId`, skill and `path` from a token with the same `sub`, no `act` and the non-delegable `human:confirm` scope, after which a fresh admission runs and the record carries `confirmation: "human_confirmed"`. Status: Accepted, human acceptance on 2026-10-16. Residual risk: the edge proves the token had `human:confirm` and no `act`, not that a human pressed the button; issuing that scope only to human sessions is the IdP's responsibility, and with the HS256 pilot the secret holder can issue it too. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-16.
- **Date:** 2026-10-16
- **Depends on:** ADRs 0013, 0014, 0015 e 0016 (Accepted).
- **Scope:** A2A-6: mecanismo da camada 5 da ADR 0013. Não declara skill de escrita nem runtime novo.

## Problema

A ADR 0016 deixou `input-required` só como regra normativa, porque não havia efeito irreversível
para proteger. Uma skill de escrita futura precisa de um ponto de pausa já testado, e não deve
ser a primeira a exercitá-lo. Esta fatia entrega o mecanismo, ativado por flag do host sobre a
skill de leitura existente, sem inventar efeito.

## Decisão

- **Flag do host.** `A2AGateway(confirm_skills=...)` / `ADF_A2A_CONFIRM_SKILLS` (lista separada
  por vírgula). É configuração do host, como a policy pinada; o request nunca a liga nem desliga.
  Vazia por padrão: sem flag, o comportamento é o da ADR 0016.
- **Pausa.** Request para skill marcada, sem task de confirmação, passa por payload, AuthN,
  delegação, skill/scope e policy do host, e então para **antes** de PDP, PEP e runtime:
  `deny`, `effect: "none"`, `reason_code: input_required`, Task
  `{"kind": "task", "id", "status": {"state": "input-required"}}`, record com `task_id` e sem
  bundle. Mesmo um token humano precisa de duas etapas: a primeira sempre pausa.
- **Confirmação.** `message/send` com `message.taskId`, mesma skill e mesmo `path`, de um token
  com o mesmo `sub`, **sem `act`** e com scope `human:confirm` (`CONFIRM_SCOPE`). `human:confirm`
  não está em `DELEGABLE_SCOPES`: um token delegado que o carregue cai em
  `scope_escalation_denied`. Faltando o scope ou havendo `act` → 403
  `human_confirmation_required`, sem consumir a task. Outro `sub` → 409
  `task_principal_mismatch`; outra skill/path → 409 `task_binding_mismatch`.
- **Retomada = admissão nova.** A confirmação válida consome a task (uma vez, TTL 300 s, mesmo
  store da ADR 0016) e roda PDP → PEP → runtime → bundle normalmente. O record dessa admissão
  leva `confirmation: "human_confirmed"` ao lado do `reason_code` do adapter. Replay → 409
  `task_not_found`; task vencida → 409 `task_expired`.
- **Tipos de task não se trocam.** Uma task `auth-required` retomada numa skill marcada não vale
  como confirmação: pausa de novo em `input-required`. Store cheio → `deny input_required` sem
  task e sem efeito.

## Contratos

Aditivo: `confirmation` opcional (`const: "human_confirmed"`) no `A2AEvidenceRecord`.
`ToolCallIntent` v1 e `CallerPrincipal` inalterados.

## Risco residual

A borda prova que o token tinha `human:confirm` e nenhum `act`, não que um humano apertou o
botão: emitir esse scope só para sessões humanas é responsabilidade do IdP. Com o piloto HS256,
quem tem o segredo também emite `human:confirm`. Store em memória, processo único (restart →
`task_not_found`). A confirmação não mostra nada ao humano: o cliente precisa exibir skill e
`path` antes de pedir o token de confirmação.

## Reversão

Esvaziar `confirm_skills` desliga a pausa. Remover o código volta à ADR 0016; records com
`confirmation` continuam válidos como histórico.
