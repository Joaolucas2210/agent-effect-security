# ADR 0006: resolução determinística de Mode e RunConfig

> **English summary.** `TaskSpec` lacks the model, adapter, toolset, runtime, hashes and limits that `RunConfig` requires, so mode selection and defaults cannot be implicit. H2-01 is a pure, deterministic transformation from a `ResolutionRequest` (explicit `requested_mode`, complete `execution_context`, allowlisted `requested_overrides`) to a closed `ResolvedRunConfig` with per-field provenance, over a versioned catalog of exactly five modes (`prototyper`, `builder`, `grower`, `sweeper`, `maintainer`); under a fixed precedence a lower layer can only keep or restrict limits, and any missing, conflicting or unknown field fails closed. Status: Accepted, approved by João Lucas on 2026-09-21. Consequence: callers must supply a complete, versioned execution context, and H2-01 neither enforces limits nor authorizes any tool, shell, network, MCP or runtime use. The full record below is in Portuguese.

- **Status:** Accepted — approved by João Lucas on 2026-09-21
- **Date:** 2026-09-21
- **Deciders:** João Lucas (approved 2026-09-21)
- **Depends on:** ADR 0005 and contracts/v1 from H1-02

## Context

ADR 0005 e a Spec aprovam cinco modos documentais — Prototyper, Builder, Grower,
Sweeper e Maintainer — e determinam que modos selecionam políticas, não agentes. A
Spec também exige uma `RunConfig` auditável, com versão, hash, limites e reserva de
verificação. H1-02 publicou os schemas de `TaskSpec`, `RunConfig` e
`ToolCapability`, mas não definiu como escolher um modo, aplicar defaults, resolver
conflitos ou preencher os campos obrigatórios de `RunConfig`.

Essa lacuna não pode ser resolvida com defaults implícitos: `TaskSpec` não contém
modelo, adapter, toolset, runtime, seus hashes, nem todos os limites requeridos por
`RunConfig`. Tampouco um modo ou uma `ToolCapability` concede autorização. Tool
Gateway, aprovação humana, execução, MCP, rede, sandbox e runtime ficam fora de
H2-01 e dependem das decisões próprias de H2-02+.

## Options considered

1. **Seleção explícita e resolução pura com contexto de execução obrigatório** —
   reproduzível, auditável e não inventa dados; exige que o chamador forneça uma
   solicitação completa.
2. **Inferir o modo por LLM ou heurística da task** — reduz entrada inicial, mas é
   ambíguo, não reproduzível e pode escolher uma postura inadequada.
3. **Preencher uma RunConfig com defaults ocultos** — parece simples, mas mascara
   modelo, runtime, hashes e limites inexistentes, contrariando a Spec.
4. **Acoplar o resolver ao Tool Gateway ou a um sandbox** — anteciparia H2-02/H3 e
   confundiria resolução de dados com autorização ou execução.

## Decision

Adotar a opção 1 para H2-01. O aceite humano explícito foi registrado neste ADR
em 2026-09-21.

### Limite de H2-01

H2-01 será uma transformação pura de dados. Ela recebe `TaskSpec`, um contexto de
execução declarado, uma solicitação explícita de modo e o catálogo versionado de
modos; devolve uma resolução serializável ou erros estruturados. Não abre arquivos
fora dos artefatos de entrada, não lê ambiente ou segredos, não chama shell, rede,
MCP, runtime ou ferramenta e não toma decisão de autorização.

`ToolCapability`, se estiver presente como referência descritiva em um contexto
futuro, não participa da resolução e nunca autoriza uma operação. `extensions` dos
contratos H1-02 permanecem informativas e não alteram seleção, precedência, limite
ou proveniência.

### Contratos conceituais de entrada e saída

H2-01 não altera, estende ou sobrecarrega o contrato publicado de `RunConfig` H1-02.
Ele define dois envelopes conceituais, que a implementação H2-01 deve versionar,
validar e testar como formatos fechados:

```text
ResolutionRequest
  - request_version
  - task_spec
  - requested_mode
  - execution_context
  - requested_overrides

ResolvedRunConfig
  - resolver_version
  - mode_id
  - mode_catalog_version
  - run_config
  - provenance
  - applied_restrictions
```

`ResolutionRequest.execution_context` fornece os campos obrigatórios de
configuração/runtime que não podem ser derivados da task. `requested_mode` é o ID
explícito escolhido pelo solicitante. `requested_overrides` é separado do envelope
de saída e só pode usar campos reais e permitidos de `RunConfig`, conforme a
allowlist desta decisão. O request não carrega segredos em claro; referências de
segredo, quando exigidas pelo campo `runtime.secret_refs`, continuam sendo apenas
referências válidas pelo schema.

Os dois envelopes são fechados: campo desconhecido é erro, nunca valor ignorado.
O formato concreto será criado somente em H2-01, com versão, validação e fixtures.
Somente `ResolvedRunConfig.run_config` valida contra
`contracts/v1/run-config.schema.json`; `mode_id`, versão de catálogo, proveniência e
restrições aplicadas pertencem exclusivamente ao envelope H2-01. Uma falha devolve
erros estruturados, não um `ResolvedRunConfig` parcialmente utilizável.

### Catálogo e seleção de mode

O catálogo inicial é versionado e contém exclusivamente estes IDs aprovados:
`prototyper`, `builder`, `grower`, `sweeper` e `maintainer`. A versão do catálogo e
o identificador de cada policy entram na saída auditável. Não há aliases, novos modos
nem roteamento implícito.

O solicitante seleciona o mode explicitamente em
`ResolutionRequest.requested_mode`. H2-01 não infere mode por LLM, texto do objetivo,
heurística ou ordem de campos. Na versão inicial, os cinco modes aprovados são
selecionáveis para qualquer `TaskSpec` válida: não há inferência task → mode nem
matriz heurística de compatibilidade. A resolução falha somente para mode ausente,
desconhecido, duplicado ou em conflito com uma restrição explícita e versionada do
`ResolutionRequest` ou `execution_context`. Uma matriz futura exige novo ADR, fonte
normativa e fixtures de avaliação.

O catálogo mapeia as posturas já aprovadas, sem transformar nenhuma delas em
permissão:

| Mode | Objetivo/postura | Contexto simbólico | Verificação simbólica |
| --- | --- | --- | --- |
| `prototyper` | experimentação reversível | task + arquivos relevantes | gate funcional mínimo e gates de entrega do repositório |
| `builder` | implementação a partir de spec/diff/dependências | spec, diff e dependências diretas | gates obrigatórios e revisão conforme risco |
| `grower` | melhoria guiada por baseline, dataset e traces | baseline, dataset, traces e configuração | eval antes da mudança e comparação pareada |
| `sweeper` | simplificação com comportamento preservado | diff, grafo, usos, métricas e RTK | mesmos testes; ampliação de escopo bloqueada |
| `maintainer` | fronteiras de confiança, confiabilidade e escala | dependências, auditorias e fronteiras de confiança | checks estritos; requisitos humanos continuam externos |

Os identificadores de `context_policy` e `verification_policy` definidos pelo
catálogo são políticas simbólicas versionadas. A implementação futura não poderá
interpretá-los como autorização de contexto, ferramenta ou runtime.

### Entradas completas e precedência

`execution_context` é distinto de `task_spec` e deve fornecer e validar todos os
campos de `RunConfig` não derivados da task ou do catálogo: `run_id`, `model`,
`adapter`, `toolset`, `runtime`, `budget`, `seed`, `experiment_id`, `trial_id`,
`policy_hash` e hashes/referências exigidos pelo schema. Em especial,
`TaskSpec.task_id` e `revision` podem originar `task_ref.id` e `task_ref.revision`,
mas `task_ref.sha256` não pode ser inventado; deve vir de uma referência imutável
validada pelo contexto de execução. `policy_hash` também vem de política/contexto
versionado, nunca de placeholder. O descritor `runtime` é dado de configuração; sua
preparação, execução e enforcement permanecem fora de H2-01.

O resolvedor valida a existência, tipo e compatibilidade de todas as entradas antes
de materializar a saída. Campo obrigatório ausente, hash/referência ausente ou
inválido, conflito ou campo normativo desconhecido é erro acionável, determinístico
e fail-closed.

A precedência é fixa, da maior para a menor:

1. restrições organizacionais e do repositório;
2. ceilings de capability declarados pelo runtime;
3. restrições do mode;
4. solicitação explícita validada;
5. defaults simbólicos do mode.

Uma camada inferior só pode manter ou restringir autorização, capability ou budget
efetivos; nunca pode ampliá-los. H2-01 apenas preserva e compara os limites
declarados: a capacidade de enforce-los continua sendo responsabilidade de H2-02+.

### Overrides, budgets e proveniência

`requested_overrides` pertence a `ResolutionRequest`; `mode_id`,
`mode_catalog_version`, `provenance` e `applied_restrictions` pertencem a
`ResolvedRunConfig` e não são campos de `RunConfig`. A allowlist v1 de overrides usa
somente nomes presentes no schema: `model.parameters`, `seed`, `experiment_id`,
`trial_id` e `budget.tokens`, `budget.seconds`, `budget.tool_calls` e
`budget.cost_usd`. Cada campo de `budget` só pode reduzir um limite numérico superior
conhecido; não pode transformar `null`/unknown em uma alegação de ceiling ou ampliar
um valor superior.

São proibidos em `requested_overrides`: `schema_version`, `run_id`, todo
`task_ref`, `model.provider`, `model.id`, `model.version`, `adapter`, `mode`,
`context_policy`, `toolset`, `runtime`, `verification_policy`, `policy_hash`,
`extensions`, hashes, identidade e limites superiores. Mode, runtime, adapter,
toolset, hashes, identidade, capability, autorização e limites superiores não podem
ser ampliados por mode, task ou override. Campo não existente no schema, campo do
envelope colocado como override ou campo fora da allowlist é erro, não é ignorado.

H2-01 não cria limites numéricos. O catálogo registra apenas a postura de orçamento
aprovada (curto por run, reservado para verificação, por trial/experimento, explícito
com benefício medido ou por auditoria). Limites numéricos vêm do contexto/runtime
validado; valores desconhecidos permanecem `null` somente onde o schema permite.
H2-02+ será responsável por materializar e enforcear ceilings reais.

Cada campo efetivo terá uma entrada de proveniência com a fonte
`runtime_constraint`, `mode_default`, `explicit_request` ou `task_derived`, a versão
da policy/contexto aplicável e as restrições superiores consideradas. A proveniência
não inclui segredos nem conteúdo de contexto. Uma restrição de mode que apenas limita
um valor é registrada como restrição aplicada, sem se passar por concessão de
autorização.

### Resultado e falhas

A saída de sucesso contém `resolver_version`, versão/ID do catálogo, `RunConfig`
efetiva e a proveniência por campo. A `RunConfig` efetiva deve validar contra
`contracts/v1/run-config.schema.json`. A saída de erro contém código estável, campo
ou regra aplicável e mensagem acionável; não contém uma configuração parcial que
possa ser executada. A mesma entrada canônica produz exatamente a mesma saída.

## Rejected decisions

- Seleção heurística de mode por LLM ou texto da task.
- Defaults ocultos para campos obrigatórios de `RunConfig`.
- Usar `ToolCapability` para autorizar execução.
- Limites numéricos sem uma fonte normativa ou runtime declarado.
- Tool Gateway, sandbox, MCP, shell, rede, execução ou aprovação humana como parte de
  H2-01.

## Consequences

- Positiva: uma futura implementação consegue resolver e auditar configurações sem
  presumir provider, permissão ou execução.
- Positiva: dados incompletos e conflitos falham antes de qualquer efeito.
- Negativa: o chamador precisa fornecer um contexto de execução completo e versionado.
- Negativa: H2-01 não torna um limite enforceable nem uma ferramenta permitida.
- Reversibilidade: barata enquanto o catálogo e o resolvedor ainda não são
  consumidores públicos; qualquer alteração semântica posterior exige versionamento,
  fixtures de compatibilidade e aprovação humana.

## Acceptance criteria for H2-01 implementation

- Catálogo contém somente os cinco modes aprovados, com versão e fixtures para cada
  resolução esperada.
- Entrada completa, explícita e validada; ausência, conflito, mode desconhecido ou
  incompatibilidade declarada falha fechada.
- Precedência e allowlist de overrides são testadas, incluindo tentativa de ampliar
  budget/capability e campo normativo desconhecido.
- Toda saída efetiva tem proveniência por campo e é idêntica para entradas idênticas.
- Saída de sucesso valida contra `RunConfig`; saída de falha não inclui configuração
  utilizável.
- Testes demonstram ausência de subprocesso, shell, rede, MCP, execução e decisão de
  autorização.
- Schemas e oráculos H1-02 permanecem inalterados e seus testes continuam verdes.

## Metrics impact

H2-01 acrescenta somente evidência determinística de seleção, proveniência e falha de
resolução. Não mede nem declara tokens, custo, execução, chamadas de ferramenta ou
enforcement de runtime. Esses valores continuam `null`/unknown quando não fornecidos
pelo contexto apropriado.

## Approval and follow-up

O aceite deste ADR autoriza somente a implementação H2-01 da resolução de mode e
`RunConfig` descrita aqui. Ele não autoriza Tool Gateway, autorização de ferramentas,
aprovação humana operacional, sandbox, MCP, shell, rede ou execução/runtime; esses
itens continuam bloqueados até ADR próprio de H2-02+. Depois de H2-01, um ADR
complementar para runtime/políticas continua sendo pré-requisito para H2-02 Tool
Gateway.
