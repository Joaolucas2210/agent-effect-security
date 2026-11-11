# Contratos públicos

[English](PUBLIC-CONTRACTS.md) · **Português (Brasil)**

Em que um integrador pode confiar no ADF `0.2.0`, como cada superfície é versionada, como falha e qual teste a
sustenta. Tudo aqui roda no host: **nenhum endpoint remoto, nenhum serviço de control plane, nenhum SaaS.** A borda
A2A escuta só em loopback. O que cada borda não cobre está na [matriz de suporte do BOUNDARY](BOUNDARY.pt-BR.md#matriz-de-suporte);
as afirmações que o ADF faz são só as da [ADR 0026](../../ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md).

## Política de compatibilidade

- O projeto segue [Semantic Versioning](https://semver.org/). Enquanto a versão for `0.x`, **uma release minor pode
  mudar um contrato**; a entrada do [CHANGELOG](../../CHANGELOG.md) diz quando isso acontece. Uma release patch não muda.
- Um contrato é versionado pelo campo dentro do documento (`schema_version`, `decision_version`, `result_version`,
  `policy_version`, `protocolVersion`), não pela versão do pacote. Um leitor deve rejeitar uma versão que não conhece.
- Todo JSON schema abaixo é fechado (`additionalProperties: false`): um campo desconhecido é erro, não ponto de extensão.
- **Níveis de estabilidade usados neste documento:**
  - **Versionado**: muda só com um novo valor de versão ou com uma minor `0.x` anunciada no CHANGELOG.
  - **Experimental**: pode mudar ou sumir em qualquer release. Tudo que se apoia em uma ADR com status *Proposed* é
    experimental. **Uma ADR Proposed não é contrato estável.**

## JSON schemas

Arquivos JSON Schema draft-07 no clone do código-fonte. Estabilidade: **versionado**.

| Diretório | Schemas | Forma do `$id` | Campo de versão (valor) |
| --- | --- | --- | --- |
| `tools/v1/schemas/` | tool-profile, tool-call-intent, policy-bundle, policy-context, admission-decision, list-files-input, decision-signal, typed-question | `https://agent-flow.invalid/tools/v1/schemas/<nome>.schema.json` | `policy_version` / `decision_version` `1.0`; `schema_version` `1.0` em decision-signal e typed-question |
| `runtime/v1/schemas/` | runtime-workspace-descriptor, runtime-audit-receipt, read-result, sensitive-path-policy-v1 | `https://agent-flow.invalid/runtime/v1/schemas/<nome>.schema.json` | `result_version` `1.0` em read-result |
| `integration/v1/schemas/` | adapter-request, evidence-bundle, adapter-attempt-event, caller-principal, a2a-evidence-record, a2a-request, a2a-agent-card, evidence-trial-observation, evidence-trial-report | só o nome do arquivo (ex.: `evidence-bundle.schema.json`); adapter-attempt-event usa `https://agent-flow.invalid/integration/v1/…` | `schema_version` `1.0`; evidence-bundle `1.0` ou `1.1` |
| `integration/v2/schemas/` | attempt-timing, session-trial-report, task-evaluation | `https://agent-flow.invalid/integration/v2/…`; task-evaluation `urn:adf:task-evaluation:1.0` | `schema_version` `1.0`; session-trial-report `2.0` |
| `contracts/v1/` | context-item, eval-result, gate-result, run-config, run-event, task-spec, tool-capability (harness de desenvolvimento, fora do caminho de leitura) | ver cada arquivo | ver cada arquivo |

- Os `$id` sob `agent-flow.invalid` são identificadores, não URLs: nada é buscado.
- Evidência: as fixtures de exemplo e negativas em cada `*/v1/examples` e `*/v1/tests`; `hooks/test-local-read-adapter.sh`,
  `hooks/test-a2a-gateway.sh`, `hooks/test-tool-admission.sh`, `hooks/test-runtime-read.sh`.

## Reason codes

- **Forma**: todo `reason_code` / `stable_reason_code` casa com `^[a-z0-9_]+$` e é texto estável, seguro para
  decidir em código. Um reason code nunca carrega caminho, conteúdo ou credencial.
- **Enumerados**: a lista fechada está em `integration/v1/schemas/adapter-attempt-event.schema.json` (enum
  `payload.reason_code`). Nos demais lugares vale só o padrão; o contrato é o schema do registro que carrega o código.
- **Códigos comuns**: `host_policy_invalid` (sem política fixada válida), `scope_not_allowlisted`, `invalid_scope`,
  `sensitive_path_denied`, `adapter_failed`, `evidence_signing_unavailable`, `attempt_evidence_failed`,
  `control_plane_tampered`, `unsupported_tool`, `unexpected_tool_input`.
- Compatibilidade: adicionar um código é mudança minor `0.x`; renomear ou remover é anunciado no CHANGELOG.

## Evidência

Estabilidade: **versionado**. A evidência é gravada no host e verificada offline; nada é enviado para fora.

| Artefato | Local | Versão | Verificar |
| --- | --- | --- | --- |
| EvidenceBundle | `<evidence_dir>/<run_id>/<bundle_id>.json` (0600, criação exclusiva) | `1.0`, ou `1.1` com `delivery_mode` = `mediated` \| `gate_only` ([ADR 0029](../../ai-development-framework/docs/architecture-decision-records/0029-delivery-mode-in-evidence.md)) | `adf verify FILE` (`verify_offline`) |
| A2AEvidenceRecord | `<evidence_dir>/_a2a/<record_id>.json` | `1.0` | `adf verify FILE` (confere também o bundle ligado) |
| Journal de tentativas | `<evidence_dir>/_attempts/<attempt_id>.jsonl` | adapter-attempt-event `1.0` | schema |
| Assinatura HMAC | `<arquivo>.sig` ao lado do arquivo, quando há chave do host ([ADR 0030](../../ai-development-framework/docs/architecture-decision-records/0030-evidence-authenticity-host-key.md)) | — | `adf verify FILE --key KEYFILE` |

- `delivery_mode` diz o que o bundle prova: `mediated`, o ADF devolveu os bytes do snapshot; `gate_only`, a
  ferramenta nativa leu o arquivo e o bundle prova a decisão e uma leitura confinada do snapshot, não os bytes
  entregues (afirmação C5).
- As assinaturas são HMAC de segredo compartilhado: mostram integridade para quem tem a chave do host, não
  autenticidade pública.
- Evidência: `hooks/test-local-evidence-bundle.sh`, `hooks/test-delivery-mode.sh`, `hooks/test-evidence-signing.sh`,
  `hooks/test-a2a-gateway.sh`.

## I/O do hook

O hook `PreToolUse` para Claude Code e Codex (`adf hook`, registrado com `adf hook-snippet`). Estabilidade:
**versionado** para a forma da saída; o conjunto de ferramentas gateadas cresce por ADR.

- **Entrada** (JSON no stdin), campos lidos: `hook_event_name` (deve ser `PreToolUse`), `tool_name`, `tool_input`
  (`file_path` para `Read`; `command` e `workdir` opcional para `Bash`; o campo de caminho ou comando das ferramentas
  só-deny), `session_id` (run id), `cwd` (raiz do projeto no Codex), `agent_type` (subagente do Claude,
  [ADR 0033](../../ai-development-framework/docs/architecture-decision-records/0033-subagent-principal-propagation.md)).
  A raiz do projeto também vem de `CLAUDE_PROJECT_DIR`. Chaves desconhecidas em `tool_input` negam com
  `unexpected_tool_input`.
- **Saída** (JSON no stdout, exit 0):
  `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"|"deny", "permissionDecisionReason": "adf: <outcome>/<reason_code>[ bundle=<id>]"}}`.
  Gates só-deny nunca respondem `allow`.
- **Sem decisão**: exit 0 com **stdout vazio**. Valem as permissões normais do agente. Acontece quando o projeto não
  está em `$ADF_HOME/enabled-projects`, a ferramenta não tem gate, o executável ou os scripts do hook faltam (por
  exemplo, instalação só pelo wheel), ou um erro ocorre antes de o ADF saber que o projeto está habilitado.
- **Projeto habilitado + qualquer falha = deny** (`adapter_failed`, `host_configuration_invalid`, `control_plane_tampered`, …).
- Evidência: `hooks/test-adf-read-hook.sh`, `hooks/test-bootstrap-matrix.sh`, `hooks/test-deny-gate-journal.sh`;
  contrato de falha na [ADR 0037](../../ai-development-framework/docs/architecture-decision-records/0037-hook-bootstrap-failure-contract.md).

## CLI

`adf` ([ADR 0025](../../ai-development-framework/docs/architecture-decision-records/0025-adf-operator-cli.md)).
Estabilidade: **versionado** para nomes de comando e exit codes; as linhas legíveis no stdout podem mudar.

| Comando | Exit codes |
| --- | --- |
| `adf doctor` | 0 control plane íntegro; 1 adulterado (ou drift de MCP); **3 sem pin** (nunca verde). A linha da política de leitura é diagnóstico e não muda o código |
| `adf verify FILE [--key KEYFILE]` | 0 verificado; 1 não verificado; 2 entrada ou chave inutilizável |
| `adf key init [KEYFILE]` | 0 criada; 1 já existe (nunca sobrescrita) |
| `adf mcp pin FILE` | 0 pin impresso; 1 registro rejeitado |
| `adf mcp probe FILE [--write]` | 0 sem mudança; 1 mudou, sem pin ou inalcançável (com `--write`: 1 só se inalcançável); 2 registro rejeitado |
| `adf hook` | sempre 0 (ver [I/O do hook](#io-do-hook)) |
| `adf hook-snippet`, `adf version` | 0 |
| `adf projects …`, `adf policy build …` | os códigos do script; 2 quando rodado de um wheel sem o clone |
| `adf a2a serve` / `adf a2a mint` | 2 em erro de uso ou configuração de host inválida |
| comando desconhecido | 2 (uso) |

## Borda A2A

`adf a2a serve` ([ADRs 0013–0019](../../ai-development-framework/docs/architecture-decision-records/0013-a2a-edge-authn-authz.md), 0022).
Estabilidade: **versionado**; regras do cliente no [BOUNDARY](BOUNDARY.pt-BR.md#contrato-do-cliente-a2a).

- **Transporte**: HTTP só em `127.0.0.1` (qualquer outro endereço é recusado); TLS, se preciso, é um proxy local.
  Corpo de no máximo 64 KiB.
- **Descoberta**: `GET /.well-known/agent-card.json`, `protocolVersion` `0.3.0`. O card público não lista skill
  protegida por escopo; `agent/getAuthenticatedExtendedCard` devolve o card completo depois da AuthN.
- **JSON-RPC 2.0 em `POST /`**, schema de requisição fechado (`a2a-request.schema.json`): `message/send` com uma
  parte de dados `{"skill": "read_workspace_file", "arguments": {"path": …}}` e `taskId` opcional.
- **AuthN**: `Authorization: Bearer <JWT>`, RS256 sobre JWKS fixado ou o segredo HS256 do piloto; `iss`, `aud`,
  `exp`, `nbf`, vida ≤ 3600 s, cadeia de delegação `act` ≤ 8.
- **Modelo de erro**:
  - 200: o PDP/PEP decidiu. `result.outcome` é `delivered` ou `deny`; **200 não significa entregue**.
    `result.task.status.state` é `auth-required`, `input-required`, `completed` ou `failed` quando há tarefa.
  - 400 `parse_error` (-32700), `invalid_request`, `credential_in_payload` (-32600).
  - 401 AuthN (-32001), 403 skill/escopo (-32003), 409 tarefa (-32006), 500 `a2a_evidence_failed` (-32005),
    503 `host_policy_invalid` (-32004).
  - Só transporte (não JSON-RPC): 404, 411, 413.
- **Política do host**: lida uma vez, quando o gateway sobe, do arquivo fixado (`ADF_READ_POLICY_FILE` +
  `ADF_READ_POLICY_SHA256`) e checada contra o pin e os schemas. Sem política fixada válida, o gateway ainda serve o
  card, mas responde toda leitura com 503 `host_policy_invalid`; **nunca usa a política demo de referência**. Uma
  política editada em disco só vale depois de um restart, e só se o pin bater.
- Evidência: `hooks/test-a2a-gateway.sh`, `hooks/test-a2a-policy-source.sh`, `hooks/test-mcp-a2a-client.sh`,
  `hooks/test-a2a-live-trial.sh`.

## Seam de extensão Python: `PolicySource`

Estabilidade: **experimental**. Apoia-se na [ADR 0039](../../ai-development-framework/docs/architecture-decision-records/0039-community-extension-seams.md),
que está **Proposed**; a assinatura pode mudar ou ser removida.

- `integration.extensions.PolicySource`: um `typing.Protocol` com `load() -> (config, sha256_pin) | None`. O padrão é
  `HostPolicyFile(path, sha256)`, o mesmo arquivo + pin das variáveis de ambiente.
- Aceito por `LocalReadAdapter(..., policy_source=)` e `A2AGateway(..., policy_source=)` (só keyword, com o par
  caminho/pin em `None`). A seleção é só por argumento de construtor: nenhuma variável de ambiente, entry point ou
  registro escolhe uma source.
- Tudo que uma source devolve é copiado (deep copy) e rechecado contra o pin, o envelope e os schemas do contrato.
  Uma source que lança exceção ou devolve algo fora do contrato nega toda leitura com `host_policy_invalid`.
- `None` seleciona a demo de referência **só no adapter**; o gateway A2A recusa (503).
- A source é consultada uma vez, na construção. Não há recarga.
- Evidência: `hooks/test-extension-contracts.sh`, `hooks/test-a2a-policy-source.sh`.

## Não é contrato

- Qualquer coisa sob uma ADR Proposed (por exemplo, configuração tipada do host, ADR 0040), funções internas de
  módulo não citadas acima, linhas de log no stderr, atributos de span OpenTelemetry (uma visão, não evidência),
  nomes de arquivo em `hooks/`.
- Comportamento de cliente real além do que o [COMPATIBILITY](COMPATIBILITY.pt-BR.md) registra.
