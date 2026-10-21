# ADR 0007: admissão de chamadas de ferramenta e fronteira de enforcement

> **English summary.** Descriptive metadata (`ToolCapability`, MCP annotations, the static `mcp/servers.json` inventory) is not per-operation authorization, and no executor exists yet. H2-02 implements only a local, versioned Registry of `ToolProfile` entries and a pure, default-deny Policy Decision Point that turns a `ToolCallIntent` into an `AdmissionDecision`; in v1 only `admit_read` can be issued, `write`, `network`, `secrets` and `destructive` receive `deny(effect_not_supported_in_h2_02)`, and the PEP/Gateway and runtime are deferred to H3. Status: Accepted, approved explicitly by João Lucas on 2026-09-22; it supersedes an earlier proposed runtime and tool-policy boundary of the same date. Limit: `admit_read` is a reproducible decision, not permission to execute, and H2-02 cannot prove the absence of an external bypass because it controls no shell. The full record below is in Portuguese.

- **Status:** Accepted — approved explicitly by João Lucas on 2026-09-22
- **Date:** 2026-09-22
- **Decider:** João Lucas
- **Depends on:** ADR 0005, ADR 0006, contracts H1-02, and H2-01 integrated into `main`
- **Supersedes:** the proposed “fronteira de runtime e política de ferramentas” dated 2026-09-22, which must not be implemented

## Context

O Agent Development Harness possui contratos versionados (H1-02) e resolve
`Mode` + `RunConfig` como dados puros (H2-01), mas não decide chamadas de
ferramenta. O inventário `mcp/servers.json` e o `mcp-audit` são controles
estáticos de configuração: não são autorização por operação, não interceptam
chamadas e não constituem runtime.

Antes de existir executor ADF, H2-02 define uma interface determinística,
reproduzível e fail-closed para decidir se uma chamada **poderia** ser admitida
sob política e escopo declarados. Não executa ferramenta, abre processo, consulta
MCP, lê filesystem, acessa rede, carrega segredo ou concede aprovação humana.

`ToolCapability`, manifest e annotation MCP descrevem comportamento, não são
prova de confiança nem autorização; clientes MCP devem tratar annotations como não
confiáveis salvo servidor confiável [1]. Defesa de modelo é probabilística, ao
passo que containment exige fronteiras de ambiente, filesystem e egress [2].
Autorização crítica não pode depender de LLM, confiança declarada ou prompt [3].

## Decision

Adotar quatro responsabilidades, implementando somente Registry e PDP em H2-02:

| Camada | Responsabilidade | Estado após H2-02 |
| --- | --- | --- |
| Registry | Catálogo local, fechado e versionado de perfis de ferramenta/operação | Dados + validação |
| Policy Decision Point (PDP) | Avalia request normalizado e devolve decisão auditável | Função pura |
| Policy Enforcement Point (PEP/Gateway) | Revalida e aplica decisão imediatamente antes do efeito | Interface especificada; H3 |
| Runtime | Processos, worktree, filesystem, rede, segredos, limites, cleanup e artefatos | Fora do escopo; H3 |

“Gateway” em H2-02 é somente interface futura, nunca alegação de que o código
bloqueia processo externo. Sem executor que controle shell, não se prova ausência
de bypass externo; H2-02 prova somente que sua API não oferece rota permissiva ou
chamada de execução.

### Princípios normativos

- **Default deny:** dado ausente, extra, incompatível, não canônico, não
  versionado ou sem correspondência exata no Registry produz `deny`.
- **Descrição não é permissão:** `ToolCapability`, `extensions`, annotations MCP,
  descrição, prompt e resposta de modelo não ampliam ação, recurso, budget ou
  scope.
- **Política determinística:** H2-02 não chama LLM, classificador, serviço externo
  ou Decision Model. Heurística futura só adiciona `approval_required` ou `deny`;
  nunca torna uma decisão permissiva sem ADR, evals e calibração próprios.
- **Menor privilégio e atenuação:** cada camada posterior mantém ou restringe
  scope, efeitos e budget; nunca amplia.
- **Bindings imutáveis:** decisão vincula versões/hashes de manifest e policy,
  run, operação, scope normalizado e digest de argumentos validados.
- **Sem segredos em evidência:** segredo em claro é rejeitado antes de persistir
  digest. Auditoria guarda IDs, hashes seguros de inputs aceitos, reason codes e
  metadados redigidos; nunca argumentos, outputs ou valores de segredo.

## Contratos H2-02

Os contratos serão fechados, versionados e locais sob
`ai-development-framework/tools/v1/`; não alteram os sete schemas H1-02 e não
usam `$ref` remoto, URL dinâmica ou manifest pela rede.

### ToolProfile

Interpretação verificada e controlada pelo ADF, distinta de metadata MCP/provider:

```text
profile_version, tool_id, provider, provider_version,
source_ref, source_commit, profile_sha256,
operations[]: { operation_id, input_schema_ref, effect_classes,
resource_kind, supported_scopes, max_risk }, provenance
```

`effect_classes` são `read`, `write`, `network`, `secrets` e `destructive`; uma
operação pode ter várias e a regra mais restritiva vence. Ferramenta, operação ou
classe ausente é inválida. Shell genérico (`command: string`, `bash -c`,
interpretador ou metacaractere) não é operação H2-02 válida. H3 exigirá operação
nomeada, `argv` estruturado, executável allowlisted e enforcement no runtime.

`profile_sha256` detecta drift, não substitui confiança: a origem é local,
versionada em Git e revisada por humano. Annotation MCP só pode entrar como
evidência, nunca como classificação efetiva de risco.

### ToolCallIntent

Intenção, não execução:

```text
intent_version, intent_id, run_id, task_ref,
tool_ref { tool_id, profile_sha256 }, operation_id,
arguments, resource_scope, requested_by, policy_context_ref, provenance
```

`arguments` valida contra schema local da operação, usando objetos fechados quando
aplicável. `resource_scope` é tipado: filesystem aceita somente caminhos relativos
ao worktree lógico, sem `..`, NUL, raiz absoluta ou paths reservados; network usa
`(scheme, hostname, port)` canônico, embora H2-02 não admita rede; repository usa
revisão imutável por hash. H2-02 normaliza sintaxe apenas. Symlink, DNS, IP,
redirect e objeto real são responsabilidade do PEP/Runtime no H3 no instante do
efeito.

### PolicyBundle e PolicyContext

`PolicyBundle` é regra versionada e hashada, sem defaults implícitos, com
allowlists declarativas de perfis, operações, efeitos e seletores de recurso.
Regras organizacionais/repositório só restringem. `PolicyContext` referencia
bundle, `ResolvedRunConfig`, restrições de repositório, ceiling de runtime
declarada e aprovações apenas por referência; H2-02 não interpreta nem consome
aprovação.

Precedência, da maior para a menor:

1. restrições organizacionais e do repositório;
2. capabilities reais do runtime, quando o PEP as fornecer;
3. `PolicyBundle` determinístico;
4. restrições do mode resolvido;
5. request e scope explícitos;
6. defaults restritivos do perfil.

Capability real ausente em H2-02 é “não demonstrada”, nunca concedida.

### AdmissionDecision

O PDP produz uma decisão completa, sem estado parcial utilizável:

```text
decision_version, decision_id, outcome, stable_reason_code, applied_rule_ids,
intent_digest, effective_scope, bindings, audit_event, provenance
```

`outcome` é `deny`, `admit_read` ou `approval_required`. No v1, somente
`admit_read` é possível: operação `read` allowlisted, scope válido e sem efeito
composto. `write`, `network`, `secrets` e `destructive` recebem
`deny(effect_not_supported_in_h2_02)`. `approval_required` existe para H6/H3, mas
H2-02 não o emite para substituir `deny`, nem integra UI, token ou aprovação.

`admit_read` é decisão reproduzível, não permissão de execução. H3 converterá
decisão ainda válida em grant efêmero, revalidará bindings e executará no runtime.
Não é bearer token nem pode ser reutilizada em outro run, manifest, scope ou input.

### Regras v1 do PDP

1. Validar envelopes e hashes antes da policy.
2. Encontrar exatamente um `ToolProfile` local com `tool_id` e digest idênticos.
3. Encontrar exatamente uma operação, validar argumentos e normalizar scope.
4. Intersectar scopes/effects entre contexto, policy, mode e perfil.
5. Negar para classe além de `read`, scope vazio, conflito, input não canônico,
   segredo em claro ou regra desconhecida.
6. Emitir `AdmissionDecision` canônica, reason code estável e sem conteúdo sensível.

Não há fallback allow, seleção por similaridade, wildcard de tool/host/path,
interpretação de `extensions` ou shell indireto.

## Limite explícito entre H2-02 e H3

H2-02 cria PDP, não Gateway operacional. H3 implementará PEP/Runtime com:

- worktree/filesystem isolado, resolução física e bloqueio de symlink escape;
- processo com `argv` estruturado, binário allowlisted e ambiente mínimo;
- egress deny-by-default, revalidação de host e controle de redirect;
- credenciais fora do sandbox e secret por referência limitada;
- timeout, CPU/memória/disco, cleanup, output limit e writer por run;
- revalidação no uso contra TOCTOU; e
- idempotency key e preflight impact binding antes de writes, com aprovação humana
  vinculada ao mesmo input/scope/hash e expirada antes da execução.

Prompts e classificadores ajudam, mas não substituem limites de ambiente e egress
[2]. A direção preserva contexto e feedback versionados no repositório, sem
acoplamento do core a vendor [4][5].

## Rejected decisions

- Modelo “System-One” tipado em H2-02: adiciona superfície probabilística,
  threshold e calibração sem traces/evals que o sustentem.
- Hash de manifest como confiança única: fixa bytes, não aprova conteúdo nem
  protege efeito futuro; Git/revisão + PEP + runtime são necessários.
- `ToolCapability`/annotation MCP como permissão; executar `read` real em H2-02;
  OPA, broker, banco de policy, servidor MCP ou serviço externo; shell arbitrário
  por conveniência. Nenhum tem consumidor ou enforcement que o justifique.

## Acceptance criteria for H2-02 implementation

### Escopo implementado

- Schemas/fixtures locais para `ToolProfile`, `ToolCallIntent`, `PolicyBundle`,
  `PolicyContext` e `AdmissionDecision`.
- Loader local de Registry e PDP puro, sem imports de subprocesso, socket, HTTP,
  MCP, Docker, Git ou ambiente.
- Perfil fixture de leitura confinada; nenhum servidor MCP real em
  `mcp/servers.json`.
- Reason codes estáveis, auditoria redigida e saída canônica para entrada canônica.

### Matriz negativa obrigatória

- tool, operação, classe, policy ou hash desconhecido; profile alterado após
  referência;
- argumentos extras/inválidos/não canônicos/com segredo em claro;
- traversal, path absoluto, NUL, scope vazio/fora da allowlist;
- host/scheme/porta inválido; extensions/annotations elevando privilégio;
- `read` composto, shell textual ou bypass por campo alternativo;
- regra ausente/conflitante e runtime capability não demonstrada;
- `deny` para `write`, `network`, `secrets` e `destructive`; e
- prova de que o módulo não chama subprocesso, shell, socket, rede, MCP ou runtime.

### Compatibilidade e validação

- Preservar H1-02, H2-01, readers/writers legados, MCP audit e inventário atual.
- Rodar Draft-07 independente, testes de contracts/eventos/modos e teste de
  admissão; skip nunca é pass.
- Não usar `make eval`/`make quality` como validação de PR documental enquanto
  gravarem `docs/evals/results.csv`; é follow-up de higiene separado.
- Nenhum processo, rede, secret, worktree, sandbox, tool call, aprovação
  operacional ou execução real aparece no diff H2-02.

## Metrics and evals

H2-02 mede cobertura de regras/contratos, decisões por reason code, determinismo,
rejeições negativas e divergência de fixture. Não mede segurança de runtime, prompt
injection em produção, custo, tokens, tool calls, latência de rede ou autonomia.

Antes de classificador/modelo entrar na policy, haverá suite de trials separada:
mesmos intents/policies, ataques documentados, grader determinístico e revisão
humana de falso allow/falso deny. Evals separam task, trial, grader, trace e estado
final [6]; pass de schema não é segurança operacional.

## Consequences

- **Positiva:** fecha a ambiguidade entre descrição e autorização e prepara PEP/
  Runtime com bindings corretos sem infraestrutura externa.
- **Custo:** o primeiro slice só admite leitura em fixture e exige dados
  versionados; escrita sem runtime confiável seria promessa de segurança falsa.
- **Reversibilidade:** sem consumidor PEP, PDP é barato de trocar. Mudança de
  semântica, effect class, profile ou policy exige versão, fixtures, PR e revisão.

## Approval and sequence

A aprovação humana explícita de João Lucas em 2026-09-22 aceita este ADR e
autoriza somente a PR H2-02 descrita. Não autoriza H3, MCP real, execução, shell,
rede, Docker, sandbox, secret manager, aprovação humana operacional ou LLM de
policy. Após integração e revisão humana de H2-02, o próximo ADR decide PEP/
Runtime H3, começando por provider local/worktree e containment observável.

## References

1. Model Context Protocol, [Tools — specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
2. Anthropic, [How we contain Claude across products](https://www.anthropic.com/engineering/how-we-contain-claude), 2026-05-25.
3. Zou et al., [Security Challenges in AI Agent Deployment](https://arxiv.org/abs/2507.20526), 2025.
4. OpenAI, [Harness engineering](https://openai.com/index/harness-engineering/), 2026-02-11.
5. OpenAI, [Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/), 2026-01-23.
6. Anthropic, [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), 2026-01-09.
7. Zhu et al., [OpenPort Protocol](https://arxiv.org/abs/2602.20196), 2026. Hipótese de design, não padrão adotado; escopo, approval vinculado, idempotência e revalidação de pré-condições ficam para H3.
