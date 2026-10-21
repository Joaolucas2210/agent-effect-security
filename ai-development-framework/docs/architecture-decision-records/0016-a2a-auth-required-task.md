# ADR 0016: A2A `auth-required` (retomada com nova admissão) e regra de `input-required`

> **English summary.** Layer 4 of ADR 0013 needs a credential that fails mid-execution to pause the task without effect, and layer 5 needs human confirmation before irreversible actions. On `principal_expired` the result is a `deny` with no content plus an A2A task in state `auth-required`; resuming with `message.taskId` reruns the whole chain from payload to evidence, and the task carries no authority, is bound to the same `sub`, `act` chain, skill and `path`, expires after 300 s and is consumed once (409 `task_not_found`, `task_expired`, `task_principal_mismatch`, `task_binding_mismatch`). For `input-required` it sets only a normative rule, with no code, because no irreversible skill exists. Status: Accepted, human acceptance on 2026-10-16. Residual risk: the task store is in memory in a single process, so a restart loses tasks (`task_not_found`), and anyone holding the token and the `task_id` can resume within the TTL. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-16.
- **Date:** 2026-10-16
- **Depends on:** ADRs 0013, 0014 e 0015 (Accepted; A2A-4 entra antes desta).
- **Scope:** A2A-5: camadas 4 e 5 da ADR 0013, sem máquina de estados genérica.

## Problema

A camada 4 pede que uma credencial que falha **durante** a execução pause a task sem efeito, e
que o cliente retome a mesma task depois de reautorizar. A camada 5 pede confirmação humana antes
de ações irreversíveis. Na borda A2A, o único efeito é a leitura confinada (reversível), e o único
ponto em que a credencial pode falhar entre admissão e efeito é o PEP: `principal_expired`
(ADR 0014), quando o token expira depois da AuthN e antes da leitura.

## Decisão proposta

### Camada 4: `auth-required`

- Se o adapter devolve `principal_expired`, o resultado é `deny`, sem conteúdo e sem efeito, e
  carrega uma Task A2A: `{"kind": "task", "id": <32 hex>, "status": {"state": "auth-required"}}`.
  O record dessa tentativa leva `task_id`.
- Para retomar, o cliente obtém um token novo fora do A2A e reenvia `message/send` com
  `message.taskId`. A retomada passa por **toda** a cadeia de novo: payload, AuthN, delegação,
  skill/scope, policy do host, PDP, PEP e evidência. A task não carrega autoridade nenhuma; só
  correlaciona.
- A task é ligada ao mesmo `sub`, à mesma skill e ao mesmo `path`, tem TTL de
  `TASK_TTL_SECONDS` (300 s) e é consumida **uma vez**. Falhas devolvem 409, com record:
  `task_not_found` (desconhecida, já consumida ou perdida num restart), `task_expired`,
  `task_principal_mismatch` e `task_binding_mismatch`. Um mismatch não consome a task, então o
  dono ainda pode retomá-la.
- A task também é ligada à cadeia `act`: outro ator delegado para o mesmo `sub` recebe
  `task_principal_mismatch`. O store tem limite de `MAX_OPEN_TASKS` (10 000); quando está cheio,
  a tentativa vira um `deny` simples, sem task e sem efeito. Negações de uma retomada antes do
  claim (scope, skill, policy) também gravam o `task_id` no record.
- O resultado da retomada traz `task.status.state` `completed` (entregue) ou `failed` (negado).
  Se o token expirar de novo no efeito, abre-se uma task nova.
- Scope ausente na requisição inicial continua 403 `insufficient_scope` (RFC 6750), não
  `auth-required`: é uma falha de pré-condição, não de execução.

### Camada 5: `input-required`

Nenhuma skill irreversível existe; `read_workspace_file` é leitura. Regra normativa: uma skill
com efeito irreversível só pode ser declarada junto com a ADR do seu efeito (`write` etc.), e ela
precisa responder `input-required`, sem efeito, até receber uma confirmação humana ligada à mesma
task, sub, skill e argumentos. A retomada segue o mesmo modelo da camada 4. Não há código para
`input-required` nesta fatia: seria especulativo sem um efeito irreversível para proteger.

## Contratos

Mudanças aditivas: `message.taskId` opcional no request A2A fechado e `task_id` opcional no
`A2AEvidenceRecord`. Requests e records antigos continuam válidos.

## Risco residual

O store de tasks fica em memória e num único processo: um restart perde as tasks, e a retomada
falha fechada (`task_not_found`). Quem tem o token e o `task_id` da vítima pode retomar dentro do
TTL, mas recebe só o que uma request nova já daria. A task não é capability. A borda continua sem
ser sandbox, e o HS256 continua sendo piloto.

## Reversão

Remover o store e o campo `taskId`: `principal_expired` volta a ser um `deny` simples (A2A-3).
Os records com `task_id` permanecem válidos como histórico.
