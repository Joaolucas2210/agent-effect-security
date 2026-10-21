# Diagnóstico: repositório vs plano de produto

[English](DIAGNOSTIC-20261020.md) · **Português (Brasil)**

Data: 2026-10-20 · Base: `main` em `91fcd18` · Categoria: *agent effect security* ([fronteira](BOUNDARY.pt-BR.md))

Objetivo: comparar o que está em `main` com o [roadmap](ROADMAP.pt-BR.md) e o [plano](IMPLEMENTATION_PLAN.pt-BR.md),
listar lacunas, regressões, riscos residuais e testes instáveis, e decidir o que ainda vale implementar
sem sair do wedge (negar e provar leituras sensíveis no host do desenvolvedor).

## Gates executados nesta base

| Gate | Resultado |
| --- | --- |
| `test-a2a-gateway.sh` (50) · `test-local-read-adapter.sh` (22) · `test-adf-read-hook.sh` (7) | verde |
| `test-codex-bash-read-gate.sh` (2) · `test-policy-pack.sh` (5) · `test-local-edge-otel.sh` (6) · `test-a2a-live-trial.sh` (3) | verde |
| `test-run-events.sh` (18) | verde nesta execução; sem reprodução da instabilidade relatada |
| `make quality-check` · `make eval-required` | verde (JS coverage, madge e stryker continuam *skipped* por ausência das ferramentas, como antes) |

## Checagens

| Checagem | Estado | Evidência |
| --- | --- | --- |
| Integridade do wedge (só efeito `read`) | OK | O PDP nega `write`/`network`/`destructive`/`secrets` com `effect_not_supported_in_h2_02`; nenhuma borda nova; o gateway continua só em `127.0.0.1` (`make_server` recusa outro host). |
| WP1b: deny do PDP anterior ao scope verifica offline | **Fechado** | Schema do bundle aceita `effective_scope: null` (#75); T5d do trial ao vivo espera `200 invalid_scope`; CONTROL_PLANE já descreve o limite estreito (admit com scope `null` continua inválido). Residual documentado: denies de contrato (`invalid_referenced_contract`, 400 A2A) não geram bundle, porque a request nunca validou. |
| REQ-MP-01: fail-safe, não-git, allowlist | OK, com lacuna de UX | Fail-safe vive na linha de registro (`[ -f … ] || exit 0`), não no repo; projeto listado sem git → `deny project_not_git`; linha não canônica nunca ativa. **Lacuna:** ativar/desativar só editando `~/.adf/enabled-projects` à mão; não há visão agregada dos reason codes em `~/.adf/evidence/`. |
| OTel local + A2A | OK | `test-local-edge-otel` prova decisão idêntica com collector fora/caindo; payload sem path/`command`/`session_id` (ADR 0021). Spans não são autoridade (BOUNDARY). |
| Trials | OK | `make a2a-live-trial` tem self-test verde; piloto multi-projeto documentado em `trials.md`. Trial ao vivo não reexecutado neste diagnóstico (opcional). |
| Flaky `test-run-events` | não reproduzido | 18/18 verde em uma execução. Se voltar a falhar, abrir issue e corrigir em PR isolado; não misturar com feature. |
| Drift de docs | pequeno | ROADMAP "Next" já marca WP1b/WP4/WP5 como done; falta registrar os itens abaixo e o one-pager de operação para partner. |

## Lacunas abertas (prioridade do goal)

| Item | Estado em `main` | Decisão |
| --- | --- | --- |
| P0 · Provar o deny (WP1b) | entregue em #75 | nada a fazer |
| P0 · UX de portfólio (list/enable/disable + agregado de reason codes) | ausente | implementar: `hooks/adf-projects.py` + `make projects*` (PR separado) |
| P1 · Simetria Codex para MP-01 | ausente (`trials.md`: "Codex ainda não tem o wrapper equivalente") | implementar: `adf-read-hook.py` despacha `Bash`→gate Codex pelo mesmo allowlist e evidência do host (PR separado) |
| P1 · Step-up vinculado ao efeito | **quase entregue** (ADRs 0016/0018): retomada exige mesmo `sub`, skill, `path`, TTL 300 s, consumo único; `task_binding_mismatch` testado | lacuna: o record da pausa não carrega o descritor do efeito, então o auditor não prova offline que o que foi confirmado é o que foi pausado. Implementar `effect_binding` (digest) nos records de pausa e retomada, ADR aditivo |
| P2 · Docs | drift pequeno | atualizar ROADMAP/PLAN/ONEPAGER/BOUNDARY ao final |

## Riscos residuais (permanecem, documentados)

- O agente pode editar `~/.adf/enabled-projects` via `Bash`; a lista tira o interruptor do workspace, não o protege.
- Claude cobre só `Read`; Codex só `cat PATH` allowlisted; nenhum gate é sandbox de host.
- Bearer A2A roubado vale até `exp`; HS256 só piloto.
- Pré-decisão (400/401 A2A, deny de contrato) continua sem record/bundle.

## Fora deste ciclo

WP6 (escrita), WP7 (DPoP/mTLS/Token Exchange), UI/gateway cloud, instalar o ADF em cada repo,
default-on global. Qualquer um deles entra só com ADR `Accepted` e demanda registrada no plano.
