# ADR 0014: envelope CallerPrincipal para admissão e evidência

> **English summary.** ADR 0013 kept the claims (`sub`, `scope`, `act`) out of the closed `ToolCallIntent` v1, so identity was lost after the edge. The decision adds a parallel, closed `CallerPrincipal` 1.0 envelope created only by the A2A gateway: the PDP rejects an invalid principal with `invalid_principal` but does not use its fields, the PEP rechecks the schema and `expires_at` (`principal_expired`), each A2A request past AuthN writes a closed `A2AEvidenceRecord` 1.0 next to the unchanged `EvidenceBundle`, and `read_workspace_file` now runs through the existing `LocalReadAdapter`; local edges keep `principal=None`. Status: Accepted, human acceptance on 2026-10-14 (A2A-3 in main, #56). Residual risk: content leaves over loopback HTTP to any holder of a valid token and scope, and without sender binding a stolen token produces evidence in the name of its `sub`. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-14 (A2A-3 em main, #56).
- **Date:** 2026-10-14
- **Depends on:** ADRs 0008, 0009, 0011, 0013 (Accepted).
- **Scope:** A2A-3: identidade da borda A2A chega a PDP, PEP e Evidence sem tocar no `ToolCallIntent` v1.

## Problema

A ADR 0013 tirou as claims (`sub`, `scope`, `act`) do `ToolCallIntent` v1, que é fechado e
compartilhado com os gates Claude/Codex. Mas o A2A-3 precisa que a identidade sobreviva até
o efeito e chegue à auditoria. Sem um portador, ela se perde depois da borda.

## Decisão proposta

Um envelope paralelo e fechado, `CallerPrincipal` 1.0
(`integration/v1/schemas/caller-principal.schema.json`):

```text
schema_version, sub, scopes[], act[] (≤ 8), token_aud, authn_method, expires_at
```

- **Origem:** só o gateway A2A cria o envelope, depois de AuthN e do pré-check de scope. O
  cliente nunca envia um principal; o corpo JSON-RPC continua fechado (ADR 0013).
- **PDP:** `decide(..., principal=None)`. Se o principal estiver presente e for inválido, a
  decisão é `invalid_principal`. Se for válido, o PDP v1 não usa os campos: quem decide o
  efeito é a policy pinada do host. O PDP segue puro e sem relógio. Ter scope nunca contorna o PDP.
- **PEP:** no momento do efeito, revalida o schema do principal e a validade temporal
  (`expires_at` > agora; senão `principal_expired`) antes das revalidações já existentes.
  O binding skill ↔ recurso é o próprio binding intent ↔ decisão ↔ operação pinada do PEP
  (a skill mapeia para uma única operação do host). A decisão consumida continua sem
  autorizar um segundo efeito (lei do P0).
- **Evidence:** o `EvidenceBundle` v1 não muda. Cada request A2A que passou da AuthN grava um
  `A2AEvidenceRecord` 1.0 fechado (edge `a2a`, skill, principal redigido, outcome,
  `reason_code`, `decision_id`/`bundle_id`, `created_at`, `record_id` = SHA-256 canônico), com
  permissões `0700`/`0600` e sem sobrescrita, ao lado do bundle. A verificação offline confere o
  record, o vínculo com o bundle e o `verify_offline` do bundle. Token bruto nunca é gravado.
  Uma falha AuthN (401) não tem identidade, então gera só a linha de log sem credencial.
- **Bordas locais (Claude/Codex/MCP):** `principal=None`, mesmo comportamento e mesmos bytes de
  decisão de antes.
- **Efeito:** `read_workspace_file` passa a usar o `LocalReadAdapter` existente (workspace
  efêmero, PEP, runtime confinado, bundle, cleanup). Repositório, revision, evidence, budget e
  policy são do host; o cliente fornece só `path`. Nenhuma classe de efeito nova.

## Compatibilidade

Mudança aditiva em v1: `invalid_principal` (PDP/PEP) e `principal_expired` (PEP) entram no enum
de `reason_code` do `AdapterAttemptEvent`, no mapping de métricas (`invalid_contract` e
`binding_mismatch`) e no oracle normativo. A evidência existente continua válida; um verificador
anterior a esta mudança rejeita journals que contenham os códigos novos.

## Fora de escopo

Token Exchange (A2A-4), `auth-required`/`input-required` (A2A-5), regras de PDP sobre campos do
principal, JWKS/mTLS de produção, `write`/`network`.

## Risco residual

O conteúdo lido sai pelo HTTP de loopback para quem tem token e scope válidos e path admitido;
é texto não confiável (`cannot_authorize`). O record prova o que a borda viu, não a origem do
token: sem binding de sender, um token roubado gera evidência em nome do `sub`. Os hashes não
autenticam a origem contra o mesmo UID. A borda continua sem ser sandbox.

## Reversão

Voltar o gateway para só decisão e remover o parâmetro opcional `principal` (PDP/PEP/adapter).
Os contratos v1 ficam intactos; os records já gravados permanecem como histórico.
