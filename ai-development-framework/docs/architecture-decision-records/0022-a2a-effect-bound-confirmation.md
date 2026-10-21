# ADR 0022: `effect_binding` — a confirmação prova a que efeito se vinculou

> **English summary.** ADR 0018 binds the resumption to the same `sub`, skill and `path`, but the pause record did not carry the effect descriptor, so an auditor had to trust the gateway that the confirmed effect was the paused one. The decision adds `effect_binding = sha256(canonical({"sub", "skill", "path"}))`, computed by the gateway and never sent by the client, to the `A2AEvidenceRecord` and response `audit` of the `input_required` pause, the `human_confirmed` resumption and resumption denials; the schema makes `confirmation` require `effect_binding`. Status: Accepted, human acceptance on 2026-10-20 (implementation merged in PR #84). Residual risk: it proves the edge saw the same `sub`, skill and `path` in both steps, not that the human read what they confirmed, and it binds the path rather than a content digest, so the file can change between pause and resumption. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-20 (implementação mergeada no PR #84).
- **Date:** 2026-10-20
- **Depends on:** ADRs 0016 e 0018 (Accepted). Aditivo; não altera o fluxo de pausa/retomada.
- **Scope:** records da borda A2A. Sem novo effect class, sem passkey, sem produto de aprovação.

## Problema

A ADR 0018 já vincula a retomada ao mesmo `sub`, skill e `path`, com TTL e consumo único, e nega
`task_binding_mismatch` quando os argumentos divergem. Mas o record da pausa não carrega o descritor
do efeito: um auditor com os records em mãos vê `input_required` + `task_id` e depois
`read_delivered` + `confirmation: human_confirmed` + `task_id`, e precisa confiar no gateway para saber
que o efeito confirmado é o que foi pausado. A pesquisa sobre aprovação de agentes insiste no oposto:
a aprovação deve ser ligada a um descritor fechado do efeito, verificável fora do caminho quente
(substituição e replay como classe de ataque).

## Decisão

- `effect_binding = sha256(canonical({"sub", "skill", "path"}))`, calculado pelo gateway a cada request
  após AuthN e validação do request, nunca enviado pelo cliente.
- Aparece no `A2AEvidenceRecord` e no `audit` da resposta em três lugares: a pausa (`input_required`),
  a retomada confirmada (`confirmation: human_confirmed`, mesmo valor) e o deny de retomada
  (`task_binding_mismatch`, `task_principal_mismatch`, `human_confirmation_required`…, com o binding do
  que foi **tentado**). Records sem pausa/retomada não ganham o campo.
- Schema: `effect_binding` opcional (hash); `confirmation` exige `effect_binding`
  (`dependencies`). Um record confirmado sem binding não verifica.
- O cliente mostra ao humano skill e `path` e pode conferir o `effect_binding` da pausa contra o da
  confirmação antes de aceitar o resultado.

## Contratos

Aditivo no `A2AEvidenceRecord` 1.0 (campo opcional + dependência). `ToolCallIntent`, `CallerPrincipal`
e o schema do request não mudam. Spans OTel não ganham atributo (ADR 0021: allowlist fechada).

## Risco residual

Prova que a borda viu o mesmo `sub`/skill/`path` nas duas etapas; não prova que o humano leu o que
confirmou (responsabilidade do cliente e do IdP, como na ADR 0018). O binding usa o `path` do request
já validado pelo schema (relativo, sem `..`), não um digest do conteúdo: o arquivo pode mudar entre a
pausa e a retomada, e o bundle da retomada registra o snapshot lido. Denies anteriores à AuthN
(400/401) continuam sem record.

## Reversão

Remover o campo e a dependência do schema; records antigos com `effect_binding` continuam válidos como
histórico (campo opcional).
