# Fronteira do produto

[English](BOUNDARY.md) · **Português (Brasil)**

Atualizado: 2026-10-19 · Versão 0.1.0 (experimental)

**Categoria:** *agent effect security*, um control plane local para coding agents. O ADF decide se um
efeito pedido por um agente pode acontecer, aplica a decisão no instante do efeito e deixa evidência
verificável offline. Ele não é plataforma de agentes, UI de orquestração, substituto do Langfuse,
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

## Matriz de suporte

Fora desta tabela, considere **risco residual**: o ADF não vê nem bloqueia esses caminhos.

| Borda | Superfície coberta | Versão validada | Modos de AuthN | Não coberto (residual) |
| --- | --- | --- | --- | --- |
| Claude Code | Hook `PreToolUse`, matcher `Read` | Versão não registrada nos trials (`na`): revalide o formato do payload na versão instalada | Nenhum (processo local, host confiável) | `Bash`, `Grep`, `Glob`, MCP de terceiros, subagentes com outras tools |
| Codex CLI | `PreToolUse` `Bash` com um único `cat <arquivo>` allowlisted; ativação por host pela mesma lista do Claude (REQ-MP-01) | 0.157.0 (hook global: `na`) | Nenhum (processo local) | `head`, `sed`, `rg`, `python -c`, pipes, redirecionamentos, qualquer outro comando |
| A2A (HTTP) | Skill `read_workspace_file` via `message/send` | Gateway deste repo, HTTP só em `127.0.0.1` | HS256 (**só piloto**: quem tem o segredo emite qualquer token); RS256 com JWKS pinada por SHA-256 (IdP real, sem rotação automática; [runbook](../../ai-development-framework/docs/runbooks/a2a-rs256-jwks.pt-BR.md)) | Token roubado vale até `exp` (≤ 1 h; sem DPoP/mTLS); bind público só por proxy TLS do host; tasks em memória |
| MCP stdio | Tool de leitura mediada | Sem validação em cliente Claude/Codex real | Nenhum | Igual à linha do cliente que o usa |
| Cursor | — | Sem adapter de evidência | — | Tudo |

Vulnerabilidades do próprio agente ou do IDE (bypass de permissão, CVEs do fornecedor) ficam fora do
gate. O ADF reduz o que passa pelas bordas acima; não torna o agente seguro.

## Evidência é o registro; telemetria só visualiza

| Sinal | Autoridade | Uso |
| --- | --- | --- |
| `EvidenceBundle` + `A2AEvidenceRecord` (`verify_offline`, `verify_record`) | **Registro oficial** | Auditoria, trial report, investigação |
| Spans OTel (`adf.a2a.request`, `adf.local_read.request`) no Jaeger ou Langfuse | Nenhuma | Correlacionar por `record_id` / `bundle_id`; o span pode faltar e não é assinado |
| Trace do agente no Langfuse | Nenhuma | Ver o que o agente tentou; não diz o que o ADF permitiu |

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
4. `make project-reasons` dá, por projeto, bundles, tentativas do journal (o `.env` da raiz, negado por contrato sem
   bundle, aparece aqui) e contagens por principal; com `POLICY=` mostra concedido versus não usado.
5. `make local-evidence-trial` agrega bundles do adapter local. Ele **não** conta records A2A
   (`evidence/_a2a/`). Para a borda A2A, use o `summary.json` do trial A2A.

| reason_code | Camada | Significado |
| --- | --- | --- |
| `invalid_referenced_contract` | Contrato v1 | Path fora do formato (ex.: dotfile na raiz como `.env`); sem bundle |
| `invalid_scope` | PDP | Componente `.env`/`.git` ou scope malformado |
| `scope_not_allowlisted` | PDP | Path fora da policy pinada pelo host |
| `sensitive_path_denied` | Runtime | Admitido pelo PDP, negado no efeito pela política de paths sensíveis |
| `run_binding_mismatch`, `task_ref_mismatch` | PDP / PEP | Decisão usada fora do run ou snapshot ao qual foi vinculada |
| `host_policy_invalid` | Adapter | Policy ausente, parcial ou com pin errado; nunca cai para o modo demo |
| `principal_required`, `principal_not_allowlisted`, `scope_not_allowlisted_for_principal` | PDP | Policy com `principal_rules` (ADR 0024): fechada a quem não nomeia; cada principal só lê a própria lista |

## Temas de mercado (mapeamento, não certificação)

| Tema | O que o ADF entrega | O que não entrega |
| --- | --- | --- |
| Tool misuse (OWASP Agentic / LLM) | Leitura só por PDP → PEP nas bordas cobertas | Controle de tools fora das bordas |
| Excessive agency | Policy pinada pelo host, efeito `read` apenas, budget de bytes, scopes por skill | Limites para efeitos que não existem no produto |
| Autorização em runtime fora do modelo | Decisão determinística sem LLM; conteúdo lido marcado `cannot_authorize` | Defesa contra prompt injection em geral |
| Governança com ponto de enforcement | Deny + evidência verificável por decisão | Dashboard, SSO/RBAC, relatórios de compliance |

Isso não é uma alegação de conformidade com OWASP nem com qualquer framework.
