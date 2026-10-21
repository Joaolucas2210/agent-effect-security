# Roadmap do produto

[English](ROADMAP.md) · **Português (Brasil)**

Atualizado: 2026-10-21 · Categoria: *agent effect security* ([fronteira](BOUNDARY.pt-BR.md))

Este roadmap prioriza pela dor de mercado. O histórico de engenharia (fatias H, P0, A2A) continua em
[`ai-development-framework/docs/roadmap.md`](../../ai-development-framework/docs/roadmap.md). O sequenciamento,
os critérios de aceite e os comandos de teste estão no [plano de implementação](IMPLEMENTATION_PLAN.pt-BR.md).

## Now: o wedge vendável

| Item | Dor que resolve | WP |
| --- | --- | --- |
| Posicionamento, fronteira, matriz de suporte, one-pager | O comprador precisa entender o que é coberto e o que fica residual | WP0 |
| Policy pack `effect-security-read-v0` | Agentes leem `.env`/chaves; o time precisa de uma policy pronta para pinar | WP1 |
| `make a2a-live-trial` repetível e redigido | AppSec quer deny + evidência reproduzível, não um screenshot | WP2 |
| Contrato 200 + deny; trial local não conta A2A | Cliente que lê só o status HTTP trata um deny como sucesso | WP3 |

## Next: piloto com design partners

| Item | Dor | WP |
| --- | --- | --- |
| ~~Tornar verificáveis os denies do PDP anteriores ao scope~~ **Done 2026-10-19** | Um deny de `config/.env` deve ser provável, não um 500 | WP1b |
| ~~Runbook RS256/JWKS como "piloto enterprise"~~ **Done 2026-10-19** ([runbook](../../ai-development-framework/docs/runbooks/a2a-rs256-jwks.pt-BR.md)) | HS256 não serve para IdP real | WP4 |
| ~~Spans OTel nas bordas locais~~ **Done 2026-10-20** ([ADR 0021](../../ai-development-framework/docs/architecture-decision-records/0021-local-edge-otel-spans.md)) | Ver as decisões de Claude/Codex na mesma tela que as do A2A | WP5 (opcional) |
| UX de portfólio: `make projects` / `project-enable` / `project-disable` / `project-reasons` | AppSec ativa projetos e lê contagens de `reason_code` sem editar `~/.adf` à mão | REQ-MP-02 (PR `feat/portfolio-projects-cli`) |
| Codex `cat` pelo mesmo hook global e lista do host | Quem usa Codex tinha de exportar raiz/evidência por shell | REQ-MP-03 (PR `feat/mp01-codex-symmetry`) |
| `effect_binding` nos records de pausa/confirmação A2A ([ADR 0022](../../ai-development-framework/docs/architecture-decision-records/0022-a2a-effect-bound-confirmation.md), Accepted) | Provar offline que a confirmação humana foi ligada ao efeito pausado | A2A-6b (**Done 2026-10-20**, #84) |
| Cliente A2A no host: o modelo vê `read_via_adf(path)`, nunca o bearer | O piloto colou um JWT no prompt; credencial no contexto do modelo | A2A-8 (PR `feat/mcp-a2a-client`) |
| Principal local derivado do harness (`claude:<agent_type>`) no journal e no span ([ADR 0023](../../ai-development-framework/docs/architecture-decision-records/0023-local-principal-from-host-harness.md), Accepted) | Três subagentes leram em paralelo e a evidência não dizia quem | MP-04 (PR `feat/local-principal`) |
| `principal_rules` na policy pinada: least privilege por agente decidido pelo PDP ([ADR 0024](../../ai-development-framework/docs/architecture-decision-records/0024-principal-rules-in-pinned-policy.md), Accepted) | Todo principal com `workspace:read` tinha a mesma autoridade | MP-05 (PR `feat/principal-policy`) |
| `mint --ttl` (padrão 1 h) só como dublê de IdP do piloto | Tasks venceram antes da confirmação humana | A2A-9 (PR `feat/mint-ttl`) |
| `project-reasons` com tentativas do journal e contagens por principal; `POLICY=` dá concedido versus não usado | O `.env` da raiz não aparecia no agregado; privilégio não era medido | MP-06 (PR `feat/project-reasons-principals`) |
| Métricas de design partner (trial no SHA do partner, `project-reasons` agregado) | Sem número de partner não há tese validada | Grower |

## Later: só com ADR `Accepted` e demanda registrada

| Item | Gate | WP |
| --- | --- | --- |
| Effect de escrita/edição | ADR próprio + demanda de design partner | WP6 |
| DPoP/mTLS, Agent Card assinado, Token Exchange com AS externo | ADR próprio (0019 adiou o endpoint) | WP7 |
| Proteger `~/.adf/enabled-projects` contra edição pelo agente | ADR próprio; hoje é residual declarado, sem teatro | — |
| Codex além de `cat PATH` (`head`, `sed`, pipes) | ADR próprio + demanda; cobertura total de Bash não é o produto | — |
| Orquestrador que distribui tokens; ADF como OAuth AS ou endpoint de Token Exchange; UI ou registry de agentes | Vira plataforma de agentes: fora da fronteira | — |
| Pré-checagem determinística antes da pausa `input-required` (não pedir confirmação do impossível) | ADR aditivo à 0018 | — |
| Skills e exemplo no agent card público; campo inválido no `400` | Pequeno, mas muda o contrato do card | — |

## Done fora do plano original

| Item | Dor | Ref |
| --- | --- | --- |
| Ativação multi-projeto no host (hook global + lista de projetos; ativação no host ≠ instalação em monorepo) | Usar o ADF no portfólio de repos do dev sem copiar em cada um nem negar leituras em massa | REQ-MP-01 |

## Not doing

- UI de grafo de agentes ou de orquestração dentro do repo.
- Langfuse self-hosted como parte do core (é um sink opcional, nunca autoridade).
- Bind público sem ADR (o gateway só escuta em `127.0.0.1`).
- Billing, telemetria phone-home ligada por padrão, certificação automática de compliance.
- Efeitos `network` ou `destructive`.
- Gateway MCP/A2A em nuvem como narrativa principal; instalar o ADF dentro de cada repo do cliente;
  ativação default-on em todos os diretórios (só allowlist opt-in).
- Sandbox de sistema operacional, cobertura total de `Bash`, LLM-guardião como substituto do PDP.
