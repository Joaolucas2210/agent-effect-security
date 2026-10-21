# ADR 0009: integração local de evidência do control plane

> **English summary.** The existing intent, decision, enforcement and tainted-result pieces do not yet compose into portable, verifiable evidence. H4-01 is a local, vendor-neutral adapter pipeline `ToolCallIntent` -> H2-02 PDP -> H3-01 PEP -> tainted `ReadResult` -> closed, versioned `EvidenceBundle`, with pure offline verification and a logical dry-run replay that never repeats the read; the bundle is a record, not a token or reusable authorization. Status: Accepted, approved explicitly by João Lucas on 2026-09-22, authorizing H4-01 only. Limit: the aggregated local metrics carry no content or paths and do not demonstrate certification or compliance with SOC 2 or the EU AI Act; write, shell, network, MCP and H3-02 remain out of scope. The full record below is in Portuguese.

- **Status:** Accepted — approved explicitly by João Lucas on 2026-09-22
- **Date:** 2026-09-22
- **Depends on:** ADR 0005, ADR 0006, ADR 0007, ADR 0008, H2-02 e H3-01 integrados em `main`
- **Scope authorized:** H4-01 only

## Context and problem

O Agent Development Harness (ADF) já separa intenção estruturada, decisão
determinística, enforcement local de leitura e resultado não confiável. Falta somente
definir como essas capacidades podem compor evidência portátil e verificável, sem
criar um novo agente, ampliar a superfície de efeito ou alterar contratos existentes.

Esta é uma decisão de produto interno e de segurança: a utilidade precisa ser medida
por evidência técnica verificável, não inferida de claims de compliance ou de uma
integração proprietária.

## Decision

Após aceite humano explícito, H4-01 será uma integração local, vendor-neutral e
evidence-first entre capacidades existentes:

```text
Coding-agent adapter
  -> ToolCallIntent
  -> H2-02 Registry + PDP
  -> H3-01 PEP + constrained local read runtime
  -> tainted ReadResult
  -> portable Evidence Bundle
  -> offline verification / replay
```

O ADF não será mais um framework de agentes. Ele é uma camada de controle,
enforcement e evidência para agentes de desenvolvimento já existentes. O adapter é
local e não recebe texto livre, prompt ou comando arbitrário como autorização.

Autorização permanece baseada em contratos estruturados, PDP determinístico e PEP.
`ToolCapability` descreve capability, mas não é autorização. Nenhum LLM ou
classificador decide autorização. O adapter somente compõe entradas e saídas; não
altera o PDP H2-02 nem o enforcement H3-01.

O `ReadResult` permanece tainted. Conteúdo, classificação e proveniência de leitura
nunca podem alterar policy, scope, approval ou instruções de sistema. O Evidence Bundle
é registro verificável: não é token, bearer token ou autorização reutilizável.

## Scope authorized after acceptance

H4-01 poderá implementar somente:

- uma interface de adapter local, independente de Claude, Codex e Cursor;
- composição explícita de `ToolCallIntent`, H2-02, H3-01, `ReadResult` e receipt;
- um formato JSON fechado, versionado e portável para `EvidenceBundle`, sem publicar
  schema nesta decisão;
- correlação por `run_id`, `decision_id`, hashes de profile/policy, `intent_digest`,
  `workspace_id`, `snapshot_digest`, outcome e reason code;
- referência a receipt e metadados redigidos, sem conteúdo bruto;
- validação offline, pura e fail-closed do bundle;
- replay lógico/dry-run que demonstra a cadeia de decisão sem repetir o efeito de
  leitura; e
- métricas locais agregadas de decisão, binding, bundle e latência.

### Conceptual Evidence Bundle contract

O futuro `EvidenceBundle` terá envelope fechado e versionado, com no mínimo:

```text
schema_version
bundle_id
run_id
adapter_id
created_at
decision_id
decision_outcome
reason_code
profile_sha256
policy_sha256
intent_digest
operation_id
effective_scope
workspace_id
snapshot_digest
read_result_digest
read_result_classification
receipt
verification
provenance
```

O contrato futuro deverá declarar `additionalProperties: false` (ou equivalente) e
rejeitar campos desconhecidos. Evolução compatível usa extensão versionada, nunca
campos desconhecidos em uma versão existente. O ADR não publica nem altera schema.

O bundle não inclui conteúdo lido, path físico ou root físico, argumentos crus ou
segredos. `receipt` é referência e metadado redigido, não conteúdo. `verification` é
evidência e não autorização.

Todo hash deve declarar o algoritmo e a canonicalização. Para a versão inicial,
`*_sha256` e `*_digest` usam SHA-256 sobre a representação JSON canônica UTF-8 do
artefato estruturado, com chaves ordenadas, sem whitespace insignificante e sem
normalização implícita de valores. O contrato posterior deve fixar a serialização,
versão de canonicalização e domínio de cada digest antes de aceitar bundles. Bundle
inválido falha fechado na futura implementação.

### Offline verification and replay

Verificação local deve ser pura: sem rede, I/O, credenciais ou execução de ferramenta.
Ela confere versão, fechamento, presença, tipos, hashes, bindings e referência/metadata
redigida do receipt. Replay lógico/dry-run usa apenas o bundle para demonstrar a cadeia
`intent -> PDP decision -> PEP result -> evidence`; não abre arquivo, não reexecuta a
leitura e não pode produzir novo efeito nem nova autorização.

## Explicitly out of scope

H4-01 não autoriza:

- escrita, delete, rename, `chmod`, Git por adapter, shell ou comando arbitrário;
- rede, MCP real, Docker, secrets manager ou provider remoto;
- CLI pública, SDK público, dashboard, SaaS, banco centralizado, SSO, RBAC enterprise
  ou cobrança;
- integração proprietária direta com Claude, Codex ou Cursor;
- LLM ou classificador decidindo autorização;
- aprovação humana operacional;
- mudança no PDP H2-02 ou no enforcement H3-01;
- usar bundle como bearer token ou autorização futura; ou
- H3-02.

## Product metric and limits

H4-01 existe para medir valor real do produto. A futura implementação mede localmente
e de forma agregada:

```text
decisions_total
admit_read_total
deny_total
binding_mismatch_total
sensitive_path_denied_total
invalid_contract_total
evidence_bundle_valid_total
evidence_bundle_invalid_total
human_intervention_required
decision_latency_ms
```

Essas métricas não registram conteúdo, paths físicos, prompts, segredos ou código de
clientes. Elas não demonstram certificação nem conformidade automática com SOC 2 ou
EU AI Act. O ADF gera evidência técnica que pode apoiar controles futuros.

## Acceptance criteria for H4-01 implementation

Uma futura PR de implementação exige, no mínimo:

- contrato fechado e versionado para o bundle;
- oráculo normativo independente;
- validação local sem rede;
- integração determinística `H2-02 -> H3-01 -> bundle`;
- bundle verificável offline, sem I/O e sem reexecução de efeitos;
- resultado sempre tainted;
- testes negativos para bundle adulterado, hashes ou bindings divergentes, campos
  ausentes, unknown properties e tentativa de usar bundle como autorização;
- prova de que adapter não introduz shell, rede, Git, escrita, MCP ou credenciais;
- compatibilidade com H1, H2-01, H2-02 e H3-01; e
- `docs/evals/results.csv` inalterado durante as validações documentais.

## Product sequence

```text
H4-01 = internal product wedge / design-partner evidence
H4-02 = somente após uso real e avaliação de métricas
H3-02 = permanece bloqueado por ADR separado
Commercial features = decisão futura, não parte deste ADR
```

## Approval and sequence

Este ADR é `Accepted` após aprovação humana explícita. Ele autoriza somente uma PR
futura de H4-01, limitada aos critérios desta decisão; não inicia essa implementação
nem autoriza H3-02, escrita, shell, rede, MCP, Git, credenciais ou produto comercial.
