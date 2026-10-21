# ADR 0008: PEP e runtime local de leitura confinada

> **English summary.** H2-02 only decides; nothing enforces an `admit_read` decision at the moment of effect. H3-01 adds a PEP, the sole consumer of `AdmissionDecision`, that revalidates the bindings (`run_id`, `profile_sha256`, `policy_sha256`, `operation_id`, `effective_scope`, `intent_digest`), and a local runtime that performs one confined file read inside a harness-owned `RuntimeWorkspaceDescriptor`, using handle-based resolution that does not follow symlinks, denying sensitive paths under `sensitive_path_policy_v1` (`sensitive_path_denied`), and returning a `ReadResult` tainted `untrusted` with a redacted audit. Status: Accepted, re-approved explicitly by human review on 2026-09-22, authorizing H3-01 only. The record states this is not a complete sandbox or host isolation, and a control the platform cannot demonstrate must be reported as `skipped` or failed. The full record below is in Portuguese.

- **Status:** Accepted — re-approved explicitly by human review on 2026-09-22
- **Date:** 2026-09-22
- **Depends on:** ADR 0005, ADR 0006, ADR 0007 e H2-02 integrados em `main`
- **Scope authorized:** H3-01 only
- **Product-alignment review:** a revisão que invalidou o aceite anterior foi re-aprovada explicitamente por humano; este ADR autoriza somente a futura implementação H3-01.

## Context and problem

H2-02 implementa Registry e PDP puro: ele normaliza a intenção, avalia política e
produz uma `AdmissionDecision` auditável. Ele não abre arquivos, não executa efeitos
nem contém o processo que os produz. Logo:

```text
PDP != PEP != Runtime != sandbox de segurança
```

H3-01 deve provar um único vertical slice de enforcement de ponta a ponta:

```text
AdmissionDecision admit_read
-> PEP revalida bindings
-> Runtime local de leitura confinada
-> resultado marcado como conteúdo não confiável
-> auditoria redigida
```

Este slice não alega sandbox completo. Uma checagem de path no userspace da linguagem
do runtime não é isolamento total de host, processo ou usuário; isolamento forte
permanece uma decisão e implementação posterior.

## Decision

| Camada | Responsabilidade |
| --- | --- |
| PDP H2-02 | Decisão pura e auditável. |
| PEP H3-01 | Único consumidor autorizado da `AdmissionDecision`; revalida imediatamente antes do efeito. |
| Runtime local H3-01 | Executa somente leitura confinada. |
| Harness | Trata conteúdo lido como dado não confiável antes de repassá-lo ao modelo. |

H3-01 aceita somente uma decisão H2-02 com `outcome=admit_read`. `deny`,
`approval_required`, decisão ausente ou decisão que não possa ser revalidada não
produzem leitura. A decisão não é bearer token, nem autorização reutilizável.

O PEP deve revalidar contra a intenção e os artefatos efetivos, no mínimo, os bindings
reais de H2-02: `run_id`, `profile_sha256`, `policy_sha256`, `operation_id`,
`effective_scope` e `intent_digest`. O limite efetivo `max_output_bytes` também deve
ser respeitado. Ele deve recomputar `intent_digest` a partir da `ToolCallIntent`
canônica recebida. Divergência, ausência, expiração que uma política futura vier a
definir ou incapacidade de revalidar falha fechada.

No v1 não há expiração por tempo: validade depende exclusivamente da revalidação dos
bindings no momento do efeito. TTL, clock-skew policy ou campo temporal exigem contrato
versionado posterior; nenhum implementador pode inventá-los.

## Product compatibility and non-goals

H3-01 é uma primitive de enforcement para uma futura camada de controle local-first e
evidence-first, vendor-neutral, para coding agents existentes. O ADF governa e produz
evidência sobre ações de Claude Code, Codex, Cursor e adapters compatíveis; ele não
substitui esses agentes nem seus runtimes.

Os artefatos já produzidos ou exigidos por H3-01 — bindings da `AdmissionDecision`,
runtime audit receipt, reason codes, proveniência e taint/classificação do conteúdo —
devem ser versionáveis e portáveis entre adapters. Isso não cria neste slice endpoint,
dashboard, serviço central, formato proprietário ou garantia de retenção enterprise.

H3-01 não é produto comercial completo, não equivale a SOC 2, EU AI Act ou certificação
de compliance, e não é sandbox completo nem proteção de host. Ele gera evidência técnica
que pode suportar controles futuros.

O diferencial técnico futuro pretendido é política reproduzível, enforcement verificável,
evidência recuperável e integração com coding agents já adotados. Não se declara como
diferencial atual Decision Model/System-One, aprovação humana operacional, SaaS control
plane, SSO/RBAC, dashboard, managed runtime ou MCP remoto. Esses itens permanecem
possibilidades posteriores, condicionadas a H4–H7, evidência de uso real e decisões próprias.

As métricas que H3-01 pode produzir honestamente são decisões admitidas/negadas por
reason code, falhas de binding, tentativas fora de scope bloqueadas, cobertura de testes
negativos e audit receipts produzidos em runs controladas. Sem dados posteriores de H4+,
não alegar incidentes evitados em produção, economia financeira, ROI, compliance certificado
ou autonomia segura em produção.

A sequência após reaprovação é:

```text
H3-01: enforcement local de read
-> H3-02: isolamento/runtime adicional, se houver evidência
-> H4: MVP interno, trials e métricas de valor
-> H5–H7: contexto, aprovação/review por risco e learning controlado
-> somente então: decisão de modelo comercial
```

Esta decisão não escolhe MIT, Apache, dual-license, SaaS ou add-ons pagos.

### Packaging, CLI and SDK follow-up

Publicar pacote npm e/ou PyPI não é autorizado por H3-01. Após a estabilização de
H2-02, uma decisão própria poderá propor uma superfície pública inicial limitada a
contratos, PDP puro e CLI de validação/decisão (`doctor`, `contracts validate`,
`policy decide` e `audit verify`). Essa superfície não executa efeitos.
`audit verify` verifica somente estrutura, hashes e bindings do receipt; não reexecuta
operação nem atua como PEP.

Os contratos JSON são a fonte de verdade do core; implementações por linguagem os
consomem sem acoplamento a Jev/Laya. Runtime que produz efeito, inclusive a leitura
confinada, só pode estar em pacote ou módulo separado após este ADR ser aceito e H3-01
ser implementado com seus testes negativos. Publicação npm/PyPI exige conta do
mantenedor, 2FA e CI; não depende de aprovação externa do registry, mas exige aprovação
humana dos ADRs antes de expor enforcement. A versão permanece `0.x` enquanto contratos
e H3 estabilizam; mudança incompatível de contrato exige major.

### Context graph boundary

Graphify, ou outro grafo de contexto, é insumo de contexto do Harness, não superfície
de enforcement deste slice. O ADF não reimplementa a CLI/skill Graphify nem faz do grafo
parte do PDP, PEP ou Runtime. H5 é o ponto para consumir grafo fresco com hash e
proveniência; uma CLI `adf` futura pode no máximo checar/orquestrar presença, freshness e
path de `graphify-out/` para o Harness, mediante decisão própria.

## Scope v1

H3-01 permite exclusivamente uma leitura de arquivo dentro de um root de workspace
explicitamente declarado e já existente. O agente nunca cria worktree. Antes do PEP,
o Harness/host prepara um workspace temporário, identificado e pertencente ao run; o
Runtime apenas o consome. Duas runs não podem alterar o checkout original, e cleanup
só remove workspace pertencente ao run. Não há root implícito nem variável de ambiente
como fonte de autorização.

São proibidos neste slice: shell, subprocesso, comando arbitrário, escrita, deleção,
renomeação, `chmod`, rede, MCP real, Docker, secrets manager, variáveis de ambiente
como fonte de autorização, worktree criado pelo agente e aprovação humana operacional.
Não introduzir provider remoto e não usar `mcp/servers.json` como executor.

Git não é ferramenta disponível ao agente e não pode ser chamado pelo PEP ou Runtime
durante a decisão/leitura. O Workspace Manager confiável pode criar e remover um
worktree detached antes da execução, exclusivamente para o lifecycle do run, com
ownership e cleanup testáveis.

### RuntimeWorkspaceDescriptor

H3-01 define um descritor conceitual, criado por componente confiável do Harness/host
antes do PEP, sem alterar os schemas H2-02:

```text
RuntimeWorkspaceDescriptor
  workspace_id
  canonical_root
  task_ref
  snapshot_digest
  ownership
  lifecycle
```

No v1, `ToolCallIntent.task_ref` de H2-02 é o digest canônico do snapshot, não o ID
lógico da task. `RuntimeWorkspaceDescriptor.task_ref` e `snapshot_digest` devem ser
exatamente iguais a ele, usando o mesmo algoritmo e representação canônica. Divergência
é `deny`; uma semântica que separe identidade da task e digest do snapshot exige contrato
versionado posterior. O PEP só lê se descriptor, intenção e resolução confiável apontarem
para o mesmo snapshot/revisão.

`ownership` tem valor único `harness_owned`. `lifecycle` é
`ephemeral_prepared`, `pending_cleanup` ou `cleaned`; somente
`ephemeral_prepared` pode produzir leitura. Root ausente ou divergente, descriptor fora
desses valores, ou qualquer vínculo não revalidável produz `deny`.
`canonical_root` é dado do descriptor, não argumento do agente e não é autorização por
si só. Um cwd, root ou descriptor alternativo apresentado pelo agente é ignorado e
produz `deny(workspace_binding_mismatch)`.

### ReadResult

O Runtime retorna um envelope conceitual, sem alterar os schemas H2-02:

```text
ReadResult
  outcome: delivered | deny
  reason_code
  content_ref ou bytes (somente quando delivered)
  byte_length
  taint: untrusted
  content_class
  provenance
  audit_ref
  decision_id, run_id, workspace_id, snapshot_digest
```

`ReadResult.outcome` descreve o resultado do efeito e não renomeia o
`AdmissionDecision.outcome=admit_read`. Em `deny`, não há `content_ref` nem bytes. O
Harness só pode repassar conteúdo ao modelo quando `outcome=delivered` e
`taint=untrusted`; `audit_ref` aponta para receipt redigido, nunca para conteúdo bruto.

## Filesystem boundary

H3-01 deve especificar e testar os seguintes requisitos antes de existir código:

- paths são relativos ao `canonical_root` do descriptor;
- negar path absoluto, `..`, NUL, path vazio e paths reservados;
- a implementação deve resolver cada componente relativamente a handles, sem seguir
  symlink (por exemplo, `openat`/`O_NOFOLLOW` aplicado por componente, ou primitive
  equivalente suportada), e validar pelo handle aberto que o alvo é regular e permanece
  no root autorizado; não pode haver segundo lookup ou check-then-open sobre path string;
- se a plataforma não oferecer essa primitive e validação por handle, o controle é
  `skipped` ou falha, nunca enforcement demonstrado;
- admitir somente arquivo regular e recusar diretório, FIFO, device e socket;
- negar arquivos sensíveis conforme artefato normativo local versionado
  `sensitive_path_policy_v1`, com padrões testáveis que incluam ao menos `.env`,
  `*.pem` e `.git/`, e reason code estável `sensitive_path_denied`;
- aplicar `max_output_bytes` efetivo e falhar fechada se a plataforma não conseguir
  aplicar esse limite ou a abertura segura; H3-01 não promete timeout genérico de
  leitura local;
- após abertura segura do arquivo regular, o Runtime consulta metadata pelo descritor
  de arquivo aberto. Se o tamanho exceder `max_output_bytes`, retorna
  `deny/output_limit_exceeded` sem entregar conteúdo parcial; e
- nunca expor conteúdo de arquivo ou valor sensível em erro ou auditoria.

As fronteiras são deliberadamente distintas:

```text
normalização sintática: H2-02
resolução física e enforcement: H3-01
isolamento forte de processo/host: slice posterior
```

## Untrusted content

Conteúdo de arquivo, tool output, README, diff ou artefato externo é não confiável.
O resultado da leitura deve carregar classificação e proveniência para o Harness. Esse
conteúdo não pode modificar policy, scope, aprovação nem instruções de sistema.

Auditoria guarda somente IDs, hashes, tamanho e classificação/proveniência; não guarda
conteúdo bruto. A classificação não autoriza a leitura e não substitui os bindings do
PEP.

## TOCTOU and audit

O PEP revalida todos os bindings, recompõe o digest da intenção e valida o
`RuntimeWorkspaceDescriptor` imediatamente antes da sequência única de resolução e
abertura. Uma decisão antiga não é autorização reutilizável: qualquer mudança de run,
profile, policy, operação, scope, intenção, root ou snapshot exige nova decisão e
revalidação. H3-01 não introduz token de autorização, idempotência de escrita ou
aprovação humana, porque não executa escrita.

A auditoria mínima da futura implementação contém:

```text
decision_id
run_id
operation
effective_scope
profile/policy hash
resultado
reason_code
timestamp
tamanho/metadata redigida
```

Quando necessário para correlação, a auditoria usa `workspace_id` e
`snapshot_digest`, nunca conteúdo do arquivo nem o path físico bruto.

Após qualquer tentativa, o descriptor transita para `pending_cleanup`. Cleanup é
obrigatório para sucesso do run e só pode remover workspace `harness_owned`; se falhar,
o receipt registra `cleanup_failed`, o run não é sucesso e o workspace permanece para
reconciliação controlada, sem remoção por path arbitrário.

## Future threat matrix and tests

A futura PR H3-01 deve cobrir, no mínimo:

- `deny` nunca executa;
- decisão com binding divergente nunca executa;
- `intent_digest`, `task_ref`, snapshot ou `RuntimeWorkspaceDescriptor` divergente,
  ausente ou sem ownership/lifecycle válido nunca executa;
- path traversal, absoluto, NUL e scope vazio;
- symlink escape, target fora do root e corrida entre validação e abertura, provando que
  não há re-resolução de path string após a abertura pelo handle;
- diretório, FIFO, device e socket;
- arquivo proibido por `sensitive_path_policy_v1` com `sensitive_path_denied`, e arquivo
  acima do limite;
- `ReadResult` delivered/deny, taint obrigatório, receipt sem conteúdo e bindings de
  decisão/workspace/snapshot preservados;
- lifecycle fora de `ephemeral_prepared`, root alternativo e falha de cleanup, sendo que
  cleanup falho não produz sucesso do run;
- tentativa de shell ou campo alternativo;
- conteúdo lido marcado como não confiável;
- auditoria sem conteúdo ou segredo;
- ausência de rede, subprocesso, MCP e escrita no PEP/Runtime, e Git limitado ao
  Workspace Manager confiável antes da execução; e
- compatibilidade preservada com H1, H2-01 e H2-02.

## Rejected decisions and limits

São rejeitados: chamar H3-01 de sandbox completo; permitir shell arbitrário; usar
LLM/classificador para autorizar o read; usar manifest ou annotation MCP como
autorização; aceitar decisão sem revalidação; implementar escrita, rede ou MCP no
primeiro slice; e depender de Docker, serviço externo ou secret manager.

Também são rejeitados: empacotar ou publicar runtime que produz efeito antes do aceite
deste ADR e dos testes negativos de H3-01; e tornar Graphify, ou sua reimplementação,
parte do PEP/Runtime de leitura.

O MCP inventory continua controle estático de configuração, não autorização nem
executor. O PDP continua determinístico; o PEP apenas enforce a decisão revalidada no
momento do efeito.

## Acceptance criteria for H3-01 implementation

A futura Implementation PR deve fornecer:

- PEP separado do PDP;
- runtime local mínimo;
- testes negativos de path, symlink e bindings;
- descriptor de workspace ligado a `task_ref` e snapshot, com root/ownership/lifecycle
  divergente negados;
- `ReadResult` tainted, com receipt redigido e correlação aos bindings revalidados;
- evidência de que `deny` não produz leitura;
- abertura segura por handle sem re-resolução de path, ou controle `skipped`/falho na
  plataforma que não a suporte;
- `sensitive_path_policy_v1` versionada, com `sensitive_path_denied` e testes negativos;
- auditoria redigida;
- conteúdo tainted; e
- nenhuma superfície de shell, rede ou escrita.

`max_output_bytes` e a política de arquivos sensíveis devem ter fonte normativa
versionada e testes negativos. Um controle que não possa ser demonstrado é `skipped`
ou falha, nunca evidência de isolamento.

## Approval and sequence

Este ADR está **Accepted** após reaprovação humana explícita e autoriza somente a futura
implementação H3-01; não inicia essa implementação nem autoriza H3-02, escrita, rede, Docker,
MCP real, secrets, sandbox de processo, CLI pública de runtime ou modelo comercial.
