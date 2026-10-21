# Control plane local-first e evidence-first

[English](CONTROL_PLANE.md) · **Português (Brasil)**

Data: 2026-09-25 · Versão do repositório: 0.1.0 (experimental)

Este documento descreve a visão de produto do control plane do ADF e o que dela já existe em
`main`. Cada claim aponta para código ou ADR. O que não tem ponteiro é futuro.

## Tese

Coding agents já estão adotados. O problema não é criar outro agente, e sim governar as chamadas
de ferramenta que eles fazem com uma fronteira **reproduzível, verificável e portável**:

| Pergunta | Resposta do ADF | Onde |
| --- | --- | --- |
| Esta chamada *poderia* ser admitida sob a política declarada? | PDP puro, determinístico, fail-closed | `tools/pdp.py` · ADR 0007 |
| A decisão ainda vale no instante do efeito? | PEP revalida todos os bindings e consome a decisão uma vez | `runtime/pep.py` · ADR 0008 |
| O efeito ficou dentro do que foi admitido? | Runtime de leitura confinada por handle, com política de paths sensíveis e limite de bytes | `runtime/local_read_runtime.py` · ADR 0008 |
| Dá para provar depois, sem reexecutar nada? | `EvidenceBundle` fechado, `verify_offline` e `logical_replay` sem I/O | `integration/local_evidence_bundle.py` · ADR 0009 |
| O que medir para saber se isso tem valor? | Agregados redigidos: admit/deny, binding mismatch, sensitive path, bundles válidos, latência | `integration/evidence_trial_metrics.py` · ADR 0009 |

## Princípios normativos

Extraídos dos ADRs 0007–0009. São regras de implementação, não aspirações.

1. **`PDP ≠ PEP ≠ Runtime ≠ sandbox`.** Cada camada mantém ou restringe scope, efeitos e budget; nunca amplia.
2. **Descrição não é permissão.** `ToolCapability`, `ToolProfile`, manifest, annotation MCP, `extensions`, prompt e resposta de modelo não autorizam nada. Annotation MCP entra no máximo como evidência.
3. **Default deny.** Dado ausente, extra, não canônico, não versionado, hash divergente ou sem correspondência **exata** no Registry produz `deny` com reason code estável.
4. **Decisão não é bearer token.** `admit_read` vincula `run_id`, `profile_sha256`, `policy_sha256`, `operation_id`, `effective_scope`, `max_output_bytes` e `intent_digest`. O PEP recomputa o digest e compara tudo antes de abrir o arquivo. Sem TTL no v1: validade é revalidação.
5. **Conteúdo lido é tainted.** Todo `ReadResult` carrega `taint: {classification: untrusted_workspace_file, cannot_authorize: true}`. O Harness só repassa ao modelo quando `outcome=delivered`, e o conteúdo nunca altera policy, scope ou instruções.
6. **Sem LLM no caminho crítico.** Nenhum classificador, Decision Model ou serviço externo decide autorização. Heurística futura só pode adicionar `deny` ou `approval_required`, nunca tornar algo permissivo sem ADR próprio.
7. **Evidência sem conteúdo.** Receipt e bundle guardam IDs, hashes, tamanhos, reason codes e proveniência. Nunca conteúdo, path físico, root, argumentos crus ou segredo.
8. **Skipped nunca é verde.** Um controle que a plataforma não permite demonstrar reporta `skipped` ou falha.

## As três primitivas entregues

### H2-02 · Registry + PDP

`decide(intent, profiles, policy, context, schemas)` devolve exatamente uma `AdmissionDecision`
canônica. Ordem: valida envelopes e hashes, acha exatamente um `ToolProfile` por `tool_id` +
`profile_sha256`, exatamente uma operação, rejeita argumento com nome sensível, valida argumentos
contra schema local, normaliza scope, intersecta allowlists de contexto/policy/mode/perfil, calcula
o menor `max_output_bytes`. Só `effect_classes == {read}` pode virar `admit_read`.

Não há fallback allow, wildcard, seleção por similaridade nem shell textual. O módulo não importa
subprocesso, socket, HTTP, MCP ou Git.

### H3-01 · PEP + runtime local de leitura

`PolicyEnforcementPoint.enforce_read(...)` aceita só `outcome=admit_read`, revalida contratos e
bindings, exige `RuntimeWorkspaceDescriptor` `harness_owned` em `ephemeral_prepared`, e chama
`LocalReadRuntime.read(descriptor, path, budget)`. O runtime abre cada componente do path com
`dir_fd` + `O_NOFOLLOW`, valida pelo `fstat` do handle que o alvo é regular e cabe no limite, e
nega paths sensíveis por `sensitive_path_policy_v1` (`.env`, `.env.*`, `.git`, `secrets`,
`credentials`, `id_rsa`, `*.pem`, `*.key`). Após qualquer tentativa o descriptor vai para
`pending_cleanup`; cleanup só remove worktree que o próprio `WorkspaceManager` criou.

O `WorkspaceManager` é o **único** chamador de Git, roda antes do PEP com repositório e revisão
configurados pelo host, e produz `snapshot_digest` determinístico (`git-tree-items-v1`) que o
`ToolCallIntent.task_ref` deve igualar. O agente não fornece root, revisão nem cwd.

### H4-01 · Evidence Bundle

`compose(request, schemas, pep)` roda H2-02 e, se admitido, H3-01, e devolve um `EvidenceBundle`
com `bundle_id` e `bundle_sha256` (SHA-256 sobre JSON canônico `json-c14n-v1`). `verify_offline`
confere schema, canonicalização, digests, integridade do receipt, coerência de bindings e
`read_result_digest`. `logical_replay` projeta a cadeia `intent → pdp → pep → evidence` a partir
do bundle. `is_authorization(bundle)` retorna sempre `False`.

`aggregate_trial_observations` (H4-01b) soma só observações cujo bundle verifica offline e cujo
reason code está no mapeamento versionado; inválidas contam em `evidence_bundle_invalid_total`.
`make local-evidence-pilot` (H4-01c) executa três trials sobre revisões internas e imprime só o
relatório agregado verificado.

## Métricas honestas

O que o ADF pode medir hoje, em runs controladas, de forma agregada e redigida:

```text
decisions_total · admit_read_total · deny_total
binding_mismatch_total · sensitive_path_denied_total · invalid_contract_total
evidence_bundle_valid_total · evidence_bundle_invalid_total
human_intervention_required_total · decision_latency_ms {count,sum,min,max}
```

O que **não** se afirma: incidentes evitados em produção, economia financeira, ROI, conformidade
SOC 2 ou EU AI Act, autonomia segura, cobertura de ataque real. Essas afirmações exigem trials
com design partners e dados que ainda não existem.

## O que não está no produto (neste estágio)

| Item | Estado | Condição para entrar |
| --- | --- | --- |
| `write`, `network`, `secrets`, `destructive` | `deny` por construção | ADR próprio + PEP/Runtime com idempotency key, preflight e aprovação vinculada |
| Sandbox de host/processo, Docker, gVisor | não existe | H3-02, bloqueado até evidência de uso |
| Shell, subprocesso, MCP real, secrets manager | proibidos no PDP/PEP/Runtime | ADR próprio |
| SaaS, SSO/RBAC, dashboard, banco central, cobrança | não existem | decisão comercial futura (H4+) |
| CLI pública / SDK / npm / PyPI | não publicados | decisão própria; no máximo CLI de validação sem efeitos |
| Pacote Python local (`pyproject.toml`, `make install-dev`) | instalação editável do clone, sem registry | só troca `sys.path` por import; não altera admissão, enforcement nem evidência |
| Decision Model / Jev / Laya | não usados; J0 só define uma porta tipada residual | trials, grader determinístico e calibração próprios |
| Aprovação humana operacional (`approval_required`) | enum existe, não é emitido | H6 |
| Adapter read-only para Claude Code (`Read`) | existe como gate PreToolUse opt-in; ver [Adapter read-only](#adapter-read-only-p0) | segundo adapter só quando compartilhar a mesma interface |
| Borda A2A (HTTP loopback, bearer + scopes) | A2A-1 a 6: leitura confinada via PEP com `CallerPrincipal`, evidence, delegação validada, `auth-required` retomável e `input-required` por flag do host; ver [Borda A2A](#borda-a2a-a2a-1-a-6) | endpoint de Token Exchange (ADR 0019, adiado), store de tasks compartilhado, DPoP/mTLS (A2A-8b), card assinado (A2A-9) e `write` exigem ADR própria; TLS só via proxy (A2A-8a) |

## Sinal residual tipado (J0)

`tools/decision_signal.py` define `TypedQuestion` (`yes_no`, `choice` ou `score`),
`DecisionSignal`, a porta `DecisionSignalProvider` e o provider local `NoopDecisionSignalProvider`.
Os contratos JSON v1 são fechados: não há prompt livre nem campo de autorização. O noop sempre
se abstém e não faz I/O. `request_residual` exige `enabled=True` e um `admit_read` já emitido
pelas regras duras; `deny` não chama o provider. Falha, resposta inválida ou provider ausente
resulta em abstenção. O sinal retornado não altera nem cria `AdmissionDecision`.

J0 só oferece a porta; PDP, adapter, PEP e runtime não a chamam. Portanto o fluxo atual continua
determinístico e desligado por padrão. A ideia é semelhante a System-One/JEV, sem consumir o
produto comercial Jev, Laya, LLM ou serviço externo. Um provider real e qualquer uso do sinal
em política exigem decisão e avaliação posteriores; sinal tipado não é autorização.

## Journal de tentativa do adapter (P0-A, proposta em branch)

O contrato aditivo `integration/v1/schemas/adapter-attempt-event.schema.json` registra
`started` e `completed` em `<evidence_dir>/_attempts/<attempt_id>.jsonl` para cada chamada
que chega a `LocalReadAdapter.read`. O início é persistido antes da validação/preparação;
o término só depois do cleanup. Deny pré-admissão continua sem bundle quando não há
request válida, mas tem journal redigido quando a evidência está disponível.

`verify_attempt(events, schema)` verifica estrutura, hashes e correlação offline; início
sozinho é `incomplete`, nunca sucesso. `complete` inclui negações e verifica somente
estrutura/integridade. O payload registra resultado calculado pós-cleanup e pré-retorno,
sem confirmação de recebimento pelo harness. Falha de cleanup fica no término mesmo que o receipt do
bundle tenha registrado leitura entregue; o bundle não é reescrito nem reautorizado.
Falha ao criar/finalizar journal impede entrega com `attempt_evidence_failed`.
Se fsync final e rollback por ftruncate falharem, um journal completo pode conter
resultado calculado `delivered` apesar do retorno deny; durabilidade não confirmada.

Os contadores v1 de trials continuam ingerindo somente bundles `*.json`: não incluem
journals nem passam a demonstrar sucesso final. Rejeições anteriores dos hooks e tools
não cobertas permanecem fora da captura. Detalhes, contrato e limites em
[ADR 0010 (Accepted)](architecture-decision-records/0010-adapter-attempt-lifecycle.md).

## Adapter read-only (P0)

`integration/local_read_adapter.py` compõe, para **uma** intenção de leitura, a cadeia já entregue:
`build_request` → `compose` (H2-02 → H3-01) → `verify_offline` → bundle redigido persistido em
`docs/observability/evidence/<run_id>/<bundle_id>.json` (dir `0700`, arquivo `0600`, gitignored).
O host fixa repositório, revisão, budget e diretório de evidência; o agente fornece só um path
relativo. Conteúdo sai do adapter apenas com `outcome=delivered`, sempre com `taint`
`untrusted_workspace_file`, e nunca entra no bundle. Cleanup falho retira o conteúdo e devolve
`deny(workspace_worktree_cleanup_failed)`. PDP e PEP não mudam.

`hooks/claude-code-read-gate.py` é o primeiro caminho de agente ligado: um hook
`PreToolUse` do Claude Code para a tool `Read`. Ele relativiza `file_path` lexicalmente contra o
repositório confiável (`..` sobrevive e é negado pelo contrato), usa `session_id` como `run_id`,
chama o adapter e responde `allow`/`deny` com `reason_code` e `bundle_id`. Qualquer outra tool,
campo extra em `tool_input`, path fora do root ou exceção produz `deny`.

Para usar em outro repositório, o host/wrapper configura o ambiente **antes** de iniciar o
agente ou o hook. Instale o pacote localmente com `make install-dev` e aponte o comando do hook
para o caminho absoluto de `claude-code-read-gate.py` neste clone:

```bash
export ADF_TRUSTED_REPOSITORY="${CLAUDE_PROJECT_DIR:?}"  # ou caminho absoluto do projeto
export ADF_TRUSTED_REVISION=HEAD                     # opcional; HEAD é o padrão
export ADF_EVIDENCE_DIR="$ADF_TRUSTED_REPOSITORY/.adf/evidence"
export ADF_MAX_OUTPUT_BYTES=1048576                  # opcional; 1 MiB é o padrão
```

`ADF_TRUSTED_REPOSITORY` deve ser diretório absoluto existente. Fora do layout ADF,
`ADF_EVIDENCE_DIR` também deve ser absoluto e explícito; a raiz de evidência criada pelo adapter,
os diretórios de sessão e os arquivos têm permissões `0700`, `0700` e `0600`. No layout ADF,
sem essas variáveis, valem a raiz do monorepo, `HEAD`, 1 MiB e
`docs/observability/evidence`. Se `CLAUDE_PROJECT_DIR` indicar outro projeto e não houver
`ADF_TRUSTED_REPOSITORY`, ou se a configuração for inválida, o gate nega com
`host_configuration_invalid`. Campos do payload da tool não configuram root, revisão, evidência
ou budget. O ambiente escolhe parâmetros do host; ele não é autorização por si só: PDP e PEP
continuam validando cada leitura.

### Policy do host (P0-B, opt-in na branch)

Sem configuração de policy, o adapter mantém o **demo de referência**, que sintetiza
grants para o path solicitado. Para aplicar allowlist previamente configurada, o host
fornece um JSON fechado com `schema_version: "1.0"`, `profiles` (um profile/uma operação),
`policy` e `context`, nos contratos v1 existentes. Use como referência os artefatos
em `tools/v1/examples/{tool-profile,policy-bundle,policy-context}/valid/read-worktree.json`.
O host revisa scopes exatos, budgets e bindings, e fixa o run ID do context ao session ID
do harness antes das intenções. Não há wildcard ou DSL.

```bash
export ADF_READ_POLICY_FILE=/caminho/absoluto/policy-aprovada.json
export ADF_READ_POLICY_SHA256="$(python3 -c 'import hashlib,json,os; v=json.load(open(os.environ["ADF_READ_POLICY_FILE"])); print(hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest())')"
```

Calcular o pin faz parte da configuração confiável do host; faça isso uma vez após
revisão, mantendo arquivo e pin fixos na sessão. Recalcular a cada pedido eliminaria
a detecção de troca do arquivo. Não alterar hashes internos para acomodar uma intenção.
O pin usa `json-c14n-v1`, não hash dos bytes/formatação do arquivo.

O adapter valida pin, versões, shape, schemas e hashes internos antes de preparar
workspace; configuração parcial ou inválida nega com `host_policy_invalid`, sem
fallback ao demo. Cada intenção usa cópia dos artefatos carregados, sem ampliar scope,
reescrever run ID ou modificar teto. PDP/PEP negam pedido acima do teto. Um adapter
mantém sua configuração; novo processo com pin antigo nega arquivo alterado.
Campos do payload não configuram policy. O host continua sendo a fronteira de
confiança; esses pins não contêm um agente com permissão para alterar seu ambiente.
Veja [ADR 0011 (Accepted)](architecture-decision-records/0011-pinned-host-read-policy.md).

Habilitar (opt-in, em `.claude/settings.json` ou `settings.local.json` do projeto;
substitua `ABS_ROOT` pelo resultado de `pwd -P`):

```json
{"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": "ABS_ROOT/.venv/bin/python3 ABS_ROOT/ai-development-framework/hooks/claude-code-read-gate.py"}]}]}}
```

Caminho documentado sem Claude Code (mesmo código que o hook executa):

```bash
printf '{"hook_event_name":"PreToolUse","tool_name":"Read","session_id":"manual-1","tool_input":{"file_path":"%s/README.md"}}' "$PWD" \
  | python3 ai-development-framework/hooks/claude-code-read-gate.py
ls ai-development-framework/docs/observability/evidence/manual-1/
```

O que **não** está coberto, deliberadamente:

- O hook decide `allow`/`deny`; a entrega do conteúdo ao modelo continua sendo a tool `Read`
  nativa, fora do runtime confinado. O bundle prova a decisão e uma leitura confinada do snapshot
  `HEAD`, não os bytes que o agente recebeu (o checkout pode ter mudanças não commitadas).
- Nada impede o agente de ler via `Bash`, outra tool ou outro processo. Não há claim de bypass-proof.
- Um sinal residual tipado futuro não autoriza uma leitura; regras determinísticas e PEP continuam
  obrigatórios.
- Um worktree Git por leitura (`WorkspaceManager`); custo real de latência, medido por
  `decision_latency_ms`, sem cache.
- Denies de contrato (`invalid_referenced_contract`, path com `..`) não geram bundle: a request nunca
  validou. Denies do PDP anteriores à resolução de scope (`invalid_scope`, `invalid_arguments`,
  `run_binding_mismatch`…) geram bundle com `effective_scope: null`, que verifica offline desde
  2026-10-19 (WP1b); antes contavam em `evidence_bundle_invalid_total`. Um admit com scope `null`
  continua inválido: o receipt exige o scope.
- O gate Claude Code cobre apenas `Read`; o gate Codex P4 abaixo cobre apenas o Bash allowlisted.
- Desde a ADR 0023 (Accepted) as bordas locais derivam um `CallerPrincipal` do harness (`claude:<agent_type>`);
  ele aparece no journal e no span, não no bundle, e ainda não altera a decisão.

## Codex Bash read-equivalent (P4)

Em Codex CLI 0.157.0, `PreToolUse` recebe `tool_name: "Bash"` e
`tool_input.command`; um deny usa `hookSpecificOutput.permissionDecision: "deny"`.
Após `delivered`, o hook retorna `{}` (no-block); nesta versão,
`permissionDecision: "allow"` sem `updatedInput` marca o hook como falho.
`hooks/codex-bash-read-gate.py` admite apenas `cat PATH` ou `cat -- PATH`, com um
único path literal ASCII sem expansão, opções, pipe, redirecionamento ou outro comando.
Um `cat` ambíguo, inclusive após separadores shell, é negado; comandos não `cat` retornam `{}` e seguem a política normal
de aprovação do Codex. `head`, `sed`, `awk`, `python -c` e outros meios de leitura
não entram nesta gramática.
**Codex gate covers allowlisted read-equivalent Bash, not all file access.**

O host define `ADF_TRUSTED_REPOSITORY` (diretório absoluto existente),
`ADF_EVIDENCE_DIR` (diretório absoluto), e opcionalmente `ADF_TRUSTED_REVISION`
(`HEAD`) e `ADF_MAX_OUTPUT_BYTES` (1048576). Configure-os no processo que inicia
o Codex, sem aceitar valores do agente. Path absoluto é relativizado contra a raiz;
path relativo usa o cwd da sessão Codex. O gate compartilha com Claude a validação
de settings e o adapter P0. A decisão `allow` significa que o adapter leu com sucesso
um snapshot confinado e persistiu evidência, após o qual o Bash nativo ainda executa
e entrega seus próprios bytes. O snapshot pode diferir do checkout ativo.
Se `tool_input.workdir` estiver presente, o path relativo usa esse diretório absoluto;
campos desconhecidos de uma leitura são negados. Sem as duas variáveis obrigatórias
de root e evidência, o gate Codex nega leituras com `host_configuration_invalid`.

Este repositório habilita o gate em [`.codex/hooks.json`](../../.codex/hooks.json):

```json
{"hooks":{"PreToolUse":[{"matcher":"^Bash$","hooks":[{"type":"command","command":"/bin/bash \"$(git rev-parse --show-toplevel)/ai-development-framework/hooks/codex-bash-read-gate.wrapper.sh\"","timeout":30,"statusMessage":"Checking ADF read policy"}]}]}}
```

A raiz Git resolve o comando absoluto mesmo iniciando Codex em um subdiretório.
O wrapper `hooks/codex-bash-read-gate.wrapper.sh` resolve a raiz pelo próprio script,
exporta defaults `ADF_TRUSTED_REPOSITORY=<raiz>`, `ADF_TRUSTED_REVISION=HEAD` e
`ADF_EVIDENCE_DIR=<raiz>/ai-development-framework/docs/observability/evidence`, e faz
`exec` de `<raiz>/.venv/bin/python3` com o path absoluto do gate. Overrides do host
continuam válidos; `ADF_MAX_OUTPUT_BYTES` mantém o default P3 de 1 MiB.
Crie `.venv` na raiz e execute `make install-dev` com ela ativa antes de iniciar Codex.
Não há paths específicos de máquina no config ou wrapper; o mesmo clone funciona em macOS/Linux.

O projeto `.codex/` precisa estar trusted. Abra `/hooks` no Codex CLI para revisar
e confiar na definição exata; mudanças exigem nova revisão. Hooks precisam estar
ativos (`[features] hooks = true`, padrão atual). [OpenAI Docs: Hooks](https://learn.chatgpt.com/docs/hooks)
documenta a configuração, o formato de entrada/saída e as limitações.

| Superfície | Cobertura ADF | Risco residual |
| --- | --- | --- |
| Claude Code `Read` | PDP → PEP → leitura confinada + bundle antes do `Read` nativo | `Read` nativo pode entregar bytes diferentes do snapshot |
| Codex `Bash` `cat` allowlisted | Mesma cadeia antes do Bash nativo | Bash pode entregar bytes diferentes; parser cobre só o comando literal |
| Outros caminhos (outros Bash, tools, processos) | Sem decisão ADF P4 | Podem ler arquivos sem passar pelo adapter; hooks são guardrail, não sandbox |

Teste manual do contrato do hook:

```bash
export ADF_TRUSTED_REPOSITORY="$(pwd -P)"
export ADF_EVIDENCE_DIR="$ADF_TRUSTED_REPOSITORY/ai-development-framework/docs/observability/evidence"
export ADF_TRUSTED_REVISION=HEAD
printf '{"hook_event_name":"PreToolUse","tool_name":"Bash","session_id":"manual-codex-allow","tool_input":{"command":"cat %s/README.md"}}' "$ADF_TRUSTED_REPOSITORY" \
  | .venv/bin/python3 ai-development-framework/hooks/codex-bash-read-gate.py
printf '{"hook_event_name":"PreToolUse","tool_name":"Bash","session_id":"manual-codex-deny","tool_input":{"command":"cat %s/.env"}}' "$ADF_TRUSTED_REPOSITORY" \
  | .venv/bin/python3 ai-development-framework/hooks/codex-bash-read-gate.py
printf '{"hook_event_name":"PreToolUse","tool_name":"Bash","session_id":"manual-codex-pass","tool_input":{"command":"ls -la"}}' \
  | .venv/bin/python3 ai-development-framework/hooks/codex-bash-read-gate.py
```

O primeiro e o terceiro retornam `{}`: para distinguir leitura admitida de
passthrough, confira o novo bundle em `ADF_EVIDENCE_DIR/manual-codex-allow/`. O segundo
retorna `deny` com `adf: deny/<reason_code>`.

Depois de uma sessão real, agregue a evidência sem reexecutar efeitos:

```bash
EVIDENCE_DIR=ai-development-framework/docs/observability/evidence make local-evidence-trial
```

No macOS, crie/ative `.venv` com o mesmo `python3` que o comando do hook usará,
rode `make install-dev` e confira `python -c 'import tools, runtime, integration'`.
O wrapper commitado já evita depender do `PATH` ou de exports do shell interativo
para o Python e os defaults do host. Para outro layout, ajuste a configuração revisada
pelo operador; não aceite root, revisão, evidência ou budget vindos do payload da tool.

Não coloque segredos no wrapper. Prefira evidência sob o repo ou
`~/Library/Application Support/adf/evidence`, fora de pastas sincronizadas por iCloud.
Leituras normais do repo não exigem desligar SIP nem conceder Full Disk Access. Se o
macOS negar criação de evidência (`Operation not permitted`), a leitura falha fechada
com `adapter_failed`; teste em um diretório normal sem prompts TCC, sem abrir permissões
globais. Os testes Linux CI e macOS local devem reportar qualquer plataforma indisponível
como `skipped`, nunca como verde.

## Experimento de leitura mediada (P0-C, branch separada)

O servidor MCP local opt-in `read_snapshot` devolve ao cliente de teste o
texto do próprio adapter, conferindo SHA-256 e tamanho contra o receipt da
mesma execução. Testes em memória e por stdio incluem checkout editado,
denial e configuração ausente. Isto não reclassifica os hooks `Read`/`cat`:
eles continuam `gate_only` e sem garantia de identidade dos bytes nativos.
Veja a [matriz de cobertura](integrations/coverage-2026-09-29.md) e a
[ADR 0012 (Accepted)](architecture-decision-records/0012-mediated-stdio-read.md).

## Borda A2A (A2A-1 a 6)

[ADR 0013](architecture-decision-records/0013-a2a-edge-authn-authz.md) (Accepted) e
[ADR 0014](architecture-decision-records/0014-caller-principal-envelope.md) (Accepted),
[ADR 0015](architecture-decision-records/0015-a2a-delegation-chain.md),
[ADR 0016](architecture-decision-records/0016-a2a-auth-required-task.md) e
[ADR 0017](architecture-decision-records/0017-a2a-rs256-pinned-jwks.md) (Accepted);
[ADR 0018](architecture-decision-records/0018-a2a-input-required-confirmation.md) e
[ADR 0019](architecture-decision-records/0019-a2a-token-exchange-seam.md) (Accepted). O A2A só
anuncia a autenticação exigida; quem pode fazer o quê continua sendo PDP → PEP → Evidence.
`integration/a2a_gateway.py` é uma borda de transporte e identidade, equivalente aos gates
Claude/Codex:

```text
Bearer (header) → AuthN → CallerPrincipal → skill/scope → LocalReadAdapter
  → ToolCallIntent v1 (inalterado, sem claims) + principal → PDP → PEP (revalida principal)
  → runtime confinado → EvidenceBundle v1 + A2AEvidenceRecord (evidence/_a2a/)
```

| Camada | Implementado | Residual |
| --- | --- | --- |
| 1. AuthN | `Authorization: Bearer` JWT: RS256 sobre JWKS local pinada pelo host (`ADF_A2A_JWKS_FILE` + `ADF_A2A_JWKS_SHA256`; gateway sem chave de assinatura) ou HS256 de piloto; assinatura, `alg`, `kid`, `iss`, `aud` exato, `exp`, `nbf`, `sub`; `exp` no máximo 1 h à frente (`token_lifetime_exceeded`) | sem fetch/rotação automática de JWKS; sem DPoP/mTLS (8b adiado): TLS só via proxy na frente (A2A-8a), token roubado vale até `exp` (≤ 1 h) |
| 2. AuthZ | `SKILL_SCOPES` → policy do host pinada (ADR 0011) → PDP → PEP; skill desconhecida/scope ausente nega antes do PDP | scope não admite sozinho; sem policy do host → `host_policy_invalid` (nunca modo demo) |
| 3. Delegação | `act` fechado `{sub, act?}`, sem ciclos, profundidade ≤ 8 (`delegation_chain_invalid`); token delegado limitado a `DELEGABLE_SCOPES` (`scope_escalation_denied`); `aud` exato barra passthrough; `exchange_hs256` é test double RFC 8693 (scopes ⊆ pai, `exp` ≤ pai) | endpoint de exchange e emissão RS256 adiados (ADR 0019, won't do yet: gateway não vira emissor); teto no recebimento é policy, não prova criptográfica; o emissor deve ser confiável |
| 4. `auth-required` | `principal_expired` no PEP → Task `auth-required`, sem efeito; retomada com `message.taskId` + token novo = admissão completa nova; mesma `sub`/skill/path, TTL 300 s, consumo único; 409 `task_*` | store em memória, processo único: restart → `task_not_found` |
| 5. `input-required` | skill marcada pelo host (`ADF_A2A_CONFIRM_SKILLS`) pausa antes de PDP/PEP (`input_required`, sem efeito); retomada com `taskId` por token do mesmo `sub`, sem `act`, com `human:confirm` (não delegável) = admissão nova, record `confirmation: human_confirmed`; senão 403 `human_confirmation_required` | a borda prova o scope, não o humano (cabe ao IdP); nenhuma skill irreversível existe; store em memória |

Fail-closed nesta ordem: corpo com chave sensível ou valor com forma de JWT/Bearer →
`credential_in_payload`; request fora do schema fechado (`decision_id`, bundle ou grant no corpo
incluídos) → `invalid_request`; AuthN → 401 + `WWW-Authenticate`; skill/scope → 403; então o
`LocalReadAdapter` existente (workspace efêmero do host, PDP, PEP, runtime, bundle, cleanup).

**Identidade sem tocar o intent (ADR 0014).** As claims nunca entram no `ToolCallIntent` v1. O
gateway cria um `CallerPrincipal` fechado (`sub`, `scopes`, `act`, `token_aud`, `authn_method`,
`expires_at`). O PDP valida o principal (`invalid_principal`), mas a decisão v1 é idêntica com ou
sem ele. O PEP revalida o principal no efeito (`invalid_principal`, `principal_expired`) antes dos
bindings existentes. Bordas locais passam `principal=None`, então nada muda para Claude, Codex ou MCP.
Os dois códigos novos foram adicionados ao enum do attempt journal e ao mapping de métricas;
a evidência antiga continua válida.

**Delegação (ADR 0015).** O gateway não aceita token de downstream no corpo (schema fechado,
`credential_in_payload`) e não faz chamadas de saída. O token de cada hop precisa ser emitido para
o `aud` deste gateway; o token do usuário para outro agente cai em 401. A cadeia `act` válida vai
para o principal e para o record (só os `sub`). Um token delegado com scope acima do teto do host
é negado inteiro, com record, em vez de ter o excedente ignorado. A redução de scopes na derivação
só existe no test double `exchange_hs256` (sem endpoint público); em produção cabe a um AS confiável.

**Tasks (ADR 0016).** A task só correlaciona; não carrega autoridade. Um `taskId` desconhecido,
expirado, já consumido, de outro `sub` ou com outra skill/path é negado com 409 e record, sem
chegar ao adapter. O resultado da retomada traz `task.status.state` `completed` ou `failed`.

**Resposta e evidência.** `delivered` traz `content` (texto não confiável, `cannot_authorize`),
`effect: "read"`, `taint` e `audit` (`sub`, `act`, `skill`, `outcome`, `reason_code`,
`decision_id`, `bundle_id`, `record_id`). Toda request que passou da AuthN grava um
`A2AEvidenceRecord` em `evidence/_a2a/<record_id>.json` (`0700`/`0600`, sem sobrescrita), ligado
ao bundle. `verify_record` confere schema, hash, principal, vínculo com o bundle e `verify_offline`.
Se a evidência falhar ou não verificar → `500 a2a_evidence_failed` e nenhum byte sai. A decisão
consumida não autoriza um segundo efeito. O 401 não tem identidade, então só gera a linha de log.

Residual honesto: AuthN só no transporte; skill/card ≠ autorização; a borda não é sandbox de host
e um agente com outra rota de leitura a contorna; HTTP só em `127.0.0.1`, sem TLS próprio (TLS via proxy, A2A-8a); o log
registra só método, rota e status; o record prova o que a borda viu, não a origem do token; a
cadeia `act` é afirmada pelo emissor, não verificada hop a hop; com o piloto HS256, quem tem o
segredo emite qualquer cadeia (com RS256 isso exige a chave privada do IdP); a verificação RSA é
stdlib própria, testada (mutação + oráculo `openssl`), não uma biblioteca auditada; um token roubado, inclusive derivado, vale até `exp`. Piloto
(sem `ADF_TRUSTED_REPOSITORY`, o host é o próprio clone e a evidência vai para
`docs/observability/evidence`):

```bash
export ADF_A2A_HS256_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export ADF_READ_POLICY_FILE=/abs/host-policy.json ADF_READ_POLICY_SHA256=<pin>   # policy aprova README.md
python3 -m integration.a2a_gateway serve &
TOKEN="$(python3 -m integration.a2a_gateway mint agent-alpha workspace:read)"   # dublê de IdP do piloto; 1 h por padrão, --ttl até 86400
curl -s http://127.0.0.1:8765/.well-known/agent-card.json
curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $TOKEN" -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m1","parts":[{"kind":"data","data":{"skill":"read_workspace_file","arguments":{"path":"README.md"}}}]}}}'
```

Piloto `input-required` (ADR 0018): o host marca a skill; o agente pausa, o humano confirma. Pausa,
retomada confirmada e deny de retomada levam `effect_binding` = digest de `sub` + skill + `path`
(ADR 0022, Accepted): o auditor confere offline que o efeito confirmado é o que foi pausado.

```bash
ADF_A2A_CONFIRM_SKILLS=read_workspace_file python3 -m integration.a2a_gateway serve &
MSG='{"kind":"message","role":"user","messageId":"m1","parts":[{"kind":"data","data":{"skill":"read_workspace_file","arguments":{"path":"README.md"}}}]'
TASK="$(curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $TOKEN" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"message/send\",\"params\":{\"message\":$MSG}}}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["task"]["id"])')"
HUMAN="$(python3 -m integration.a2a_gateway mint agent-alpha 'workspace:read human:confirm')"
curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $HUMAN" -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"message/send\",\"params\":{\"message\":${MSG},\"taskId\":\"$TASK\"}}}"
```

Piloto RS256 (ADR 0017): o IdP assina com a chave privada; o host pina só a JWKS pública.

```bash
export ADF_A2A_JWKS_FILE=/abs/jwks.json ADF_A2A_JWKS_SHA256="$(sha256sum /abs/jwks.json | cut -d' ' -f1)"
unset ADF_A2A_HS256_SECRET   # com JWKS configurada, HS256 nunca é aceito
python3 -m integration.a2a_gateway serve &
curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $RS256_TOKEN_FROM_IDP" -d '…'
```

**Transporte (A2A-8a).** O processo Python só escuta em `127.0.0.1` (`make_server` recusa
qualquer outro host com `loopback_only`; teste fixa isso). Para expor a borda fora da máquina,
um proxy **no mesmo host** termina TLS e encaminha para o loopback; o bind público é do proxy,
decisão do host, e não muda AuthN, PDP, PEP nem evidência. Exemplo Caddy (logs de acesso
desligados por padrão; se ligados, `Authorization` sai redigido):

```caddyfile
a2a.example.internal {
	tls /etc/adf/a2a.crt /etc/adf/a2a.key
	request_body {
		max_size 64KB
	}
	@a2a path / /.well-known/agent-card.json
	handle @a2a {
		reverse_proxy 127.0.0.1:8765
	}
	handle {
		respond 404
	}
}
```

Equivalente nginx: `listen 443 ssl; ssl_protocols TLSv1.3; client_max_body_size 64k;` e
`location = /` + `location = /.well-known/agent-card.json` com `proxy_pass http://127.0.0.1:8765;`.
Nunca coloque `$http_authorization` num `log_format`.

Residual de transporte: TLS protege o bearer em trânsito, mas não o liga ao remetente — token
roubado continua valendo até `exp` (≤ 1 h). DPoP/mTLS (A2A-8b) exigem ADR própria e ficam
adiados. O card continua anunciando `url` loopback; o cliente remoto usa a URL do proxy. O
proxy é um componente exposto novo: patch, certificados e rate limit são do host.

## Observabilidade (OTel, ADR 0020)

[ADR 0020](architecture-decision-records/0020-control-plane-otel-export.md) (Accepted). Desligado
por padrão. Com `ADF_OTEL_ENABLED=1`, cada request A2A vira um span `adf.a2a.request` enviado por
OTLP/HTTP JSON (stdlib, sem dependência) **depois** da decisão final: status, `outcome`,
`reason_code`, `skill`, `act_depth`, `task_state` e os ids `decision_id` / `bundle_id` /
`record_id`. Nunca token, `sub`, `path` nem conteúdo; valor suspeito descarta o span inteiro.
Collector fora ou exporter com erro → uma linha em stderr e a mesma resposta (fail open).

Residual: **trace ≠ evidência.** O span pode faltar e não é assinado; auditoria é o Evidence
Bundle + `verify_offline`, e métricas de trial continuam em `make local-evidence-trial`.

```bash
docker compose -f docs/observability/docker-compose.otel.yml up -d     # Jaeger, só loopback
export ADF_OTEL_ENABLED=1 ADF_OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
python3 -m integration.a2a_gateway serve &                              # + env do piloto A2A acima
BODY='{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"kind":"message","role":"user","messageId":"m1","parts":[{"kind":"data","data":{"skill":"read_workspace_file","arguments":{"path":"README.md"}}}]}}}'
curl -s -X POST http://127.0.0.1:8765/ -d "$BODY"                                                  # 401 auth_missing
curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $(python3 -m integration.a2a_gateway mint agent-alpha other:read)" -d "$BODY"  # 403
curl -s -X POST http://127.0.0.1:8765/ -H "Authorization: Bearer $TOKEN" -d "$BODY"                # 200 read_delivered
# http://127.0.0.1:16686 → service adf-control-plane → três spans adf.a2a.request
```

Com `ADF_A2A_CONFIRM_SKILLS=read_workspace_file`, a pausa aparece como `reason_code=input_required`,
`task_state=input-required`.

**Bordas locais ([ADR 0021](architecture-decision-records/0021-local-edge-otel-spans.md)).** Com o mesmo
`ADF_OTEL_ENABLED=1`, cada decisão do gate Claude `Read`, do gate Codex `cat` e da tool MCP vira um span
`adf.local_read.request` com só `adf.edge` (`claude_read` | `codex_bash` | `mcp_read`), `outcome`,
`reason_code`, `bundle_id` e `duration_ms`. Nunca `file_path`, `command`, `session_id`, raiz do repo ou
conteúdo. O hook espera o envio por no máximo `ADF_OTEL_FLUSH_MS` (padrão 300 ms, teto 2000), só com OTel
ligado, e não escreve no stderr se o export falhar. Uma leitura A2A continua gerando um span só
(`adf.a2a.request`): o `LocalReadAdapter` não exporta. Do span ao bundle: `adf.bundle_id` →
`evidence/<run_id>/<bundle_id>.json` → `verify_offline`.

**Duas telas (Langfuse + ADF).** O mesmo exporter pode mandar para o OTLP do Langfuse
(`ADF_OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel` +
`ADF_OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64(pk:sk)>`; headers só por `https` ou
loopback, nunca logados). Langfuse mostra o que o agente fez; o ADF decide e prova. Jaeger
continua funcionando. Correlação span → `evidence/_a2a/<record_id>.json` → `verify_record`:
[runbook](observability/LANGFUSE.pt-BR.md). Rodada com HTTP real, prints e benchmark:
[trials A2A ao vivo](observability/trials/a2a-live/README.md). Residual: o conteúdo dos traces do agente no Langfuse
depende da privacidade configurada na integração do agente; os spans do ADF seguem redigidos.

## Para design partners

O que o repositório oferece para avaliação hoje:

- rodar `make local-evidence-trial` (P2) e ler o agregado redigido; ver [Trial local](#trial-local-p2);
- rodar `make local-evidence-pilot` e inspecionar o relatório agregado;
- ler o [trial A2A ao vivo](observability/trials/a2a-live/README.md) (matriz T1–T7, evidência verificada,
  prints do Jaeger, benchmark) e repetir no próprio host;
- rodar a matriz negativa (`hooks/test-tool-admission.sh`, `hooks/test-runtime-read.sh`,
  `hooks/test-local-evidence-bundle.sh`) e ler os reason codes;
- ler os schemas em `tools/v1`, `runtime/v1`, `integration/v1` e os oráculos normativos em
  `*/v1/tests/normative-oracles.json`.

O que se pede em troca: intents reais (redigidos) de leitura, casos em que o `deny` estaria
errado, e a lista de arquivos sensíveis que a política v1 ainda não cobre.

### Trial local (P2)

Para instalar em outro repositório e capturar sessões reais sem misturar smoke e
evidência anterior, siga o [protocolo de coleta](trials.pt-BR.md).

`hooks/run-local-evidence-trial.py` transforma o adapter P0 e as métricas H4-01b em um trial
repetível, local e redigido. Uma fonte por execução, um só formato de relatório:

| Fonte | Comando | O que mede |
| --- | --- | --- |
| Suite fixa (`suite_version` 1.0) | `make local-evidence-trial` | cinco leituras reais do adapter sobre o checkout em `HEAD`: `README.md` (admit), `secrets/token` (sensitive path), `docs/../README.md` (traversal, deny de contrato sem bundle), binding mismatch no PDP (`run_binding_mismatch`) e no PEP (`task_ref_mismatch`) |
| Evidência persistida | `make local-evidence-trial EVIDENCE_DIR=ai-development-framework/docs/observability/evidence` | bundles já gravados pelo adapter ou pelo gate `Read` do Claude Code; nenhum PDP, PEP ou runtime é chamado |

Pré-requisitos: `make install-dev` (falha fechada com essa dica se os pacotes não importam) e,
para a segunda fonte, o gate `Read` habilitado como em [Adapter read-only](#adapter-read-only-p0).

O relatório sai em `docs/observability/trials/<trial_id>.json` (dir `0700`, arquivo `0600`,
gitignored, nunca sobrescrito) com `schema_version`, `trial_id`, `created_at`, `source`
(`kind`, `suite_version`, `adapter_id`, `adapter_version`, `package_version`,
`latency_recorded`), `reads_total`, `bundles_total`, `reason_codes` (`outcome/reason_code` →
contagem) e `metrics` (o `EvidenceTrialReport` H4-01b verificado). Não há conteúdo, path,
prompt nem argumento cru; um reason code que não case `^[a-z0-9_]+$` vira
`deny/evidence_bundle_invalid` em vez de ser ecoado.

Como ler os reason codes principais:

- `delivered/read_delivered` — leitura admitida, revalidada no PEP e entregue tainted.
- `deny/sensitive_path_denied` — admitida pelo PDP, negada no efeito pela política v1. Conta em
  `admit_read_total` **e** em `sensitive_path_denied_total`; `deny_total` é só deny de PDP.
- `deny/task_ref_mismatch`, `deny/workspace_binding_mismatch` — binding rompido no efeito; contam
  em `binding_mismatch_total`.
- `deny/run_binding_mismatch` e outros denies de PDP anteriores ao scope — bundle com
  `effective_scope: null`, verificável; contam em `deny_total` e na categoria do mapeamento
  (`binding_mismatch_total`, `invalid_contract_total`). Trials anteriores a 2026-10-19 (WP1b)
  os contavam em `evidence_bundle_invalid_total`: não compare as duas séries diretamente.
- `deny/invalid_referenced_contract` — request nunca validou; há leitura, não há bundle
  (`reads_total − bundles_total`).
- `human_intervention_required_total` conta só bundles com `approval_required`, que o PDP hoje
  não emite. Não é um fluxo de aprovação.
- `latency_recorded: false` (fonte persistida): bundles não carregam latência; o bloco
  `metrics.decision_latency_ms` contém zeros de preenchimento e deve ser ignorado.

Riscos residuais que o número não cobre: `Bash` e qualquer outra tool contornam o gate `Read`;
userspace não é sandbox de host; os dois casos de binding mismatch são injetados pela suite (o
adapter não muda); as métricas são evidência técnica de runs controladas, não compliance, ROI ou
prova de ausência de bypass.

## Referências

- ADR 0007 · [admissão e fronteira de enforcement](architecture-decision-records/0007-runtime-and-tool-policy-boundary.md)
- ADR 0008 · [PEP e runtime local de leitura confinada](architecture-decision-records/0008-pep-and-constrained-local-read-runtime.md)
- ADR 0009 · [integração local de evidência](architecture-decision-records/0009-local-control-plane-evidence-integration.md)
- [Arquitetura e diagramas](ARCHITECTURE.pt-BR.md) · [Glossário](GLOSSARY.pt-BR.md) · [Roadmap](roadmap.md)
