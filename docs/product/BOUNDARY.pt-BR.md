# Fronteira do produto

[English](BOUNDARY.md) · **Português (Brasil)**

Atualizado: 2026-11-04 · Versão deste checkout 0.2.0 (experimental)

**Categoria:** *agent effect security*, um control plane local para coding agents. Em uma borda suportada e instalada,
o ADF decide se uma leitura observada pode prosseguir e, quando o pedido chega à composição, deixa um bundle
que pode ser conferido offline. Negações anteriores podem deixar apenas journal. Ele não é plataforma de agentes, UI de orquestração, substituto do Langfuse,
marketplace MCP, sandbox de sistema operacional nem fábrica de certificação.

```text
Intent → AuthN (bordas) → scope/skill → PDP → PEP → runtime de efeito mínimo → Evidence
```

## Effects suportados

| Effect class | Estado | Onde está a regra |
| --- | --- | --- |
| `read` (arquivo regular, snapshot Git preparado pelo host) | **Suportado** | ADRs 0007, 0008, 0011 |
| `write`, `network`, `destructive`, `secrets` | **Não suportado.** O PDP nega com `effect_not_supported_in_h2_02` | Exige ADR `Accepted` próprio + demanda de design partner registrada no [plano](IMPLEMENTATION_PLAN.pt-BR.md) |

## Ativação no host

Ativação por host não é instalação em monorepo: um clone do ADF e um hook global atendem N projetos,
cada um ligado numa lista do host (`~/.adf/enabled-projects`, operada por `make projects` /
`project-enable` / `project-disable`); fora dela o ADF não decide nada. `make project-reasons` agrega os
`reason_code` por projeto a partir de `~/.adf/evidence`, só contagens.
Passo a passo em [trials.md](../../ai-development-framework/docs/trials.pt-BR.md#vários-projetos-com-um-hook-só-req-mp-01).

## Bootstrap e confiança no host

`adf hook-snippet` imprime JSON de registro; o operador deve mesclá-lo nas configurações do cliente, reiniciar o
cliente e então pinar o control plane instalado. O wrapper emitido contém `[ -x "$A" ] || exit 0`: se o executável
faltar, não há decisão ADF. `integration/cli.py` também retorna 0 sem decisão numa exceção inesperada de
`adf hook`. O dispatcher de projeto habilitado retorna deny para falhas que captura *depois* de identificar o
projeto. Esses fatos não estabelecem fail-closed para o cliente inteiro. Registro ausente, wrapper que falha,
tool não observada ou cliente que ignora a saída do hook podem seguir as regras do próprio cliente. A
[ADR 0037](../../ai-development-framework/docs/architecture-decision-records/0037-hook-bootstrap-failure-contract.md)
registra o desenho aberto e os testes de versão de cliente necessários antes de qualquer mudança semântica;
`hooks/test-hook-failure-semantics.sh` fixa o comportamento de hoje caso a caso (sem decisão vs deny, e se existe algum
registro do ADF). Ausência de registro do ADF nunca significa "bloqueado".

## Matriz de suporte

Fora desta tabela, considere **risco residual**: o ADF não vê nem bloqueia esses caminhos.

| Borda | Superfície coberta | Versão validada | Modos de AuthN | Não coberto (residual) |
| --- | --- | --- | --- | --- |
| Claude Code | Hook `PreToolUse`, matcher `Read`; deny-only em `Grep`/`Glob` (paths sensíveis), `Edit`/`Write`/`MultiEdit`/`NotebookEdit` (paths sensíveis + config de agente) e `WebFetch`/`curl`/`wget` após tentativa sensível na mesma sessão (ADR 0028 slices 1a, 1c); decisões deny-only observadas vão ao journal quando a persistência funciona | Versão não registrada nos trials (`na`): revalide o formato do payload na versão instalada | Nenhum (processo local, host confiável) | Formas de Bash fora da gramática 1b, `Grep`/`Glob` sem `path`, servers MCP fora do registry, subagentes com outras tools; gates deny-only deixam journal, nunca bundle |
| Codex CLI | `PreToolUse` `Bash`: um único `cat <arquivo>` allowlisted é admitido com bundle; leituras listadas como `head`/`tail`/`sed`/`grep`/`rg`/`awk`/… em paths sensíveis e algumas formas ambíguas de comando são negadas (ADR 0028 slice 1b); `curl`/`wget` após tentativa sensível negados (1c); ativação por host pela mesma lista do Claude (REQ-MP-01) | 0.157.0 (hook global: `na`) | Nenhum (processo local) | Scripts chamados pelo nome, APIs de interpretador fora da gramática fechada, binários de leitura não listados e comandos que não são leitura; [teste com fixture](../../ai-development-framework/hooks/test-bash-read-grammar.py) confirma que alguns retornam sem decisão ADF |
| A2A (HTTP) | Skill `read_workspace_file` via `message/send` | Gateway deste repo, HTTP só em `127.0.0.1` | HS256 (**só piloto**: quem tem o segredo emite qualquer token); RS256 com JWKS pinada por SHA-256 (IdP real, sem rotação automática; [runbook](../../ai-development-framework/docs/runbooks/a2a-rs256-jwks.pt-BR.md)) | Token roubado vale até `exp` (≤ 1 h; sem DPoP/mTLS); bind público só por proxy TLS do host; tasks em memória |
| MCP (qualquer server, Claude Code) | Deny-only: nomes de server e tool precisam estar no registry pinado pelo host; uma `definition` pinada (command/args/chaves de env) precisa bater com todos os escopos de config do Claude Code na chamada; digest da lista de tools conferido offline por `adf mcp probe` (ADR 0031 slices 1–2); tools que o host declara `write`/`network` são negadas depois que a sessão tentou um path sensível; descrições não autorizam nada | Probe validado contra o próprio server stdio deste repo; clientes de terceiros reais `na` | Nenhum | Rug-pull entre probes (`adf doctor` falha quando o último probe é mais velho que o limite do host, 30 dias por padrão); drift no `config.toml` do Codex só reportado por `adf doctor` (o Codex não manda chamadas MCP ao hook); servers iniciados fora do hook; o output do próprio server (tainted, não bloqueado) |
| MCP stdio | Tool de leitura mediada | Sem validação em cliente Claude/Codex real | Nenhum | Igual à linha do cliente que o usa |
| Cursor | — | Sem adapter de evidência | — | Tudo |

Vulnerabilidades do próprio agente ou do IDE (bypass de permissão, CVEs do fornecedor) ficam fora do
gate. O ADF reduz o que passa pelas bordas acima; não torna o agente seguro.

## Evidência é o registro; telemetria só visualiza

| Sinal | Autoridade | Uso |
| --- | --- | --- |
| `EvidenceBundle` + `A2AEvidenceRecord` (`verify_offline`, `verify_record`) | Registro de decisão composta | Auditoria, trial report, investigação; `gate_only` prova decisão e checagem do snapshot, não bytes nativos entregues; `mediated` devolve bytes controlados |
| Journal de tentativas (`_attempts/`) | Registro de tentativa pré-adapter / deny-only | Motivo e principal de uma tentativa observada; não implica bundle nem receipt de leitura |
| Spans OTel (`adf.a2a.request`, `adf.local_read.request`) no Jaeger ou Langfuse | Nenhuma | Correlacionar por `record_id` / `bundle_id`; o span pode faltar e não é assinado |
| Trace do agente no Langfuse | Nenhuma | Ver o que o agente tentou; não diz o que o ADF permitiu |

`adf verify ARQUIVO` confere schema, digests e vínculos, mas informa `authenticity=not_checked`. Com `--key`, ele
confere o sidecar HMAC usando o segredo compartilhado do host. Isso é autenticidade relativa à chave do host,
não assinatura pública nem prova para auditor independente. Não distribua a chave HMAC. A assinatura é opt-in;
um bundle não assinado ainda pode passar na checagem de integridade. A evidência pode conter scopes relativos ao
repositório e IDs; revise antes de compartilhar. A [ADR 0030](../../ai-development-framework/docs/architecture-decision-records/0030-evidence-authenticity-host-key.md)
define o esquema implementado; a [ADR 0038](../../ai-development-framework/docs/architecture-decision-records/0038-evidence-key-lifecycle.md)
registra o desenho ainda aberto para rotação e verificação por terceiros.

## Contrato do cliente A2A

- **HTTP 200 não significa leitura entregue.** Uma decisão do PDP/PEP volta como 200 com
  `result.outcome = "deny"` e um `reason_code`. O cliente precisa ler `result.outcome`.
- 401 é falha de AuthN (sem record: não há identidade); 403 é skill/scope; 400 é request fora do schema;
  409 é task inválida; 500 `a2a_evidence_failed` significa que não houve evidência verificável, então
  nenhum byte saiu.
- Exemplo: `config/.env` é negado pelo PDP (`invalid_scope`) antes de existir scope. O bundle tem
  `effective_scope: null` e verifica offline, e a borda responde 200 com `outcome=deny` e record. Até
  2026-10-19 esse caso respondia 500 (WP1b do [plano](IMPLEMENTATION_PLAN.pt-BR.md)).

## Como AppSec usa os trial reports

1. Rode a suite no SHA fixado e guarde o agregado, não os bundles brutos (podem conter nomes de arquivo).
2. Leia os `reason_codes`, não só o total de denies. `deny_total` conta só denies do PDP; denies no
   efeito aparecem em `sensitive_path_denied_total` e `binding_mismatch_total`.
3. Cobre `verify_offline` ou `verify_record` de uma amostra: um número sem bundle verificável não é prova.
4. `make project-reasons` dá, por projeto, bundles e tentativas do journal (por exemplo, traversal inválido
   negado por contrato sem bundle) e contagens por principal; com `POLICY=` mostra concedido versus não usado.
   Desde a ADR 0036, um `.env` na raiz chega ao PDP e produz bundle para a negação `invalid_scope`.
5. `make local-evidence-trial` agrega bundles do adapter local. Ele **não** conta records A2A
   (`evidence/_a2a/`). Para a borda A2A, use o `summary.json` do trial A2A.

| reason_code | Camada | Significado |
| --- | --- | --- |
| `invalid_referenced_contract` | Contrato v1 | Path fora do formato (`..`, `//`, NUL, metacaracteres de shell); sem bundle. Desde a ADR 0036 um dotfile na raiz é path válido: `.env` é deny do PDP **com** bundle |
| `invalid_scope` | PDP | Componente `.env`/`.git` (raiz ou aninhado) ou scope malformado |
| `scope_not_allowlisted` | PDP | Path fora da policy pinada pelo host |
| `sensitive_path_denied` | Runtime | Admitido pelo PDP, negado no efeito pela política de paths sensíveis |
| `run_binding_mismatch`, `task_ref_mismatch` | PDP / PEP | Decisão usada fora do run ou snapshot ao qual foi vinculada |
| `host_policy_invalid` | Adapter | Policy ausente, parcial ou com pin errado; nunca cai para o modo demo |
| `principal_required`, `principal_not_allowlisted`, `scope_not_allowlisted_for_principal` | PDP | Policy com `principal_rules` (ADR 0024): fechada a quem não nomeia; cada principal só lê a própria lista |

## Temas de mercado (mapeamento, não certificação)

| Tema | O que o ADF entrega | O que não entrega |
| --- | --- | --- |
| Tool misuse (OWASP Agentic / LLM) | Leituras admitidas passam por PDP → PEP nas bordas cobertas; outras tentativas selecionadas passam por gates deny-only | Controle de tools fora das bordas |
| Excessive agency | Policy pinada pelo host, efeito `read` apenas, budget de bytes, scopes por skill | Limites para efeitos que não existem no produto |
| Autorização em runtime fora do modelo | Decisão determinística sem LLM; conteúdo lido marcado `cannot_authorize` | Defesa contra prompt injection em geral |
| Governança com ponto de enforcement | Decisão de leitura composta tem bundle; negações observadas antes têm journal | Dashboard, SSO/RBAC, relatórios de compliance |

Isso não é uma alegação de conformidade com OWASP nem com qualquer framework.

Modelo de atacante, trust boundary e as únicas claims permitidas em texto público:
[ADR 0026](../../ai-development-framework/docs/architecture-decision-records/0026-threat-model-and-claims.md)
(Accepted). Incidentes reais mapeados para `covered | residual | out_of_scope`: [mapa de cobertura](../knowledge/coverage.md).
