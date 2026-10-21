# ADR 0020: Export de observabilidade do control plane (OpenTelemetry)

> **English summary.** The AuthN -> scope -> PDP -> PEP -> evidence flow is only legible by reading evidence files and bundles. The decision is a standard-library OTLP/HTTP JSON exporter (`integration/otel_export.py`) that emits one `adf.a2a.request` span per A2A request after the final response exists, off by default (`ADF_OTEL_ENABLED=1` turns it on), fail open for the product (the admit or deny is identical with the collector down) and fail closed for secrets (any attribute outside a closed allowlist or shaped like a credential drops the whole span). Status: Accepted, human acceptance on 2026-10-16; amended by ADR 0021 (local edges). Consequence: traces can be missing and are not signed, so they are not audit records; the Evidence Bundle plus `verify_offline` remains the source of truth, and `local_read` was left uninstrumented here. The full record below is in Portuguese.

- **Status:** Accepted — aceite humano em 2026-10-16. Amended by [ADR 0021](0021-local-edge-otel-spans.md) (bordas locais).
- **Date:** 2026-10-16
- **Depends on:** ADRs 0009, 0013–0019 (Accepted).
- **Scope:** Observabilidade P0: um span por request da borda A2A, para visualização (Jaeger).
  Não muda AuthN, PDP, PEP, runtime, evidência nem contratos.

## Problema

O fluxo AuthN → scope → PDP → PEP → efeito/deny → evidência só é legível lendo
`evidence/_a2a/` e bundles. Ops e design partners querem ver isso numa UI de mercado sem
transformar o exporter em autoridade nem em canal de vazamento.

## Opções

1. **SDK `opentelemetry-*` como extra** — padrão, batching; três dependências novas e o SDK
   aceita qualquer atributo, então a redação continuaria sendo nossa.
2. **OTLP/HTTP JSON em stdlib** — ~60 linhas, zero dependência, allowlist fechada no único ponto
   de saída. Sem batching, sem propagação de contexto.
3. **Não fazer** — evidência offline já é a fonte de verdade; perde-se só a visualização.

## Decisão

Opção 2. `integration/otel_export.py`, chamado uma vez em `A2AGateway.handle`, depois da resposta
final (e dos ids de evidência) existir.

- **Desligado por padrão.** Só `ADF_OTEL_ENABLED=1` liga. `ADF_OTEL_EXPORTER_OTLP_ENDPOINT`
  (padrão `http://127.0.0.1:4318`, só `http(s)://`), `ADF_OTEL_SERVICE_NAME`
  (padrão `adf-control-plane`). Desligado = nenhuma thread, nenhuma rede.
- **Fail open para o produto.** Envio em thread daemon, timeout 2 s; qualquer erro vira uma linha
  em stderr com o tipo da exceção (nunca a URL). A resposta e o admit/deny são os mesmos com
  export ligado, desligado ou com collector fora (teste roda a matriz A2A inteira ligado).
- **Fail closed para segredos.** Chave fora da allowlist, valor que não seja str/int/bool, ou
  valor com forma de JWT/`bearer`/`secret`/`password`/`private` → o span inteiro é descartado.
- **Export ≠ autorização.** Nada lê spans para decidir.

| Atributo (span `adf.a2a.request`) | Origem |
| --- | --- |
| `http.response.status_code`, `adf.duration_ms` | transporte |
| `adf.outcome`, `adf.reason_code`, `adf.task_state` | resposta |
| `adf.has_principal`, `adf.act_depth` | status / `audit.act` (só a profundidade) |
| `adf.skill`, `adf.decision_id`, `adf.bundle_id`, `adf.record_id`, `adf.confirmation` | `audit` |

**Proibido:** header `Authorization`, token, claims, `sub`/cadeia `act`, `path`, `content`,
corpo da request ou resposta, JWKS, policy.

## Consequências

- Positivo: fluxo visível no Jaeger (`docs/observability/docker-compose.otel.yml`); núcleo sem
  dependência nova.
- Negativo: trace não é auditoria de registro — pode faltar (collector fora, span descartado) e
  não é assinado; a fonte de verdade continua sendo o Evidence Bundle + `verify_offline`.
  `ponytail:` uma thread por span e sem spans filhos PDP/PEP; trocar por fila em lote / SDK se a
  taxa ou a necessidade de propagação de contexto aparecer. `local_read` não instrumentado.
- Reversibilidade: barata — remover a chamada em `handle`.

## Contratos

Nenhum: `ToolCallIntent` v1, `CallerPrincipal` e `A2AEvidenceRecord` inalterados. A correlação
trace ↔ evidência é por `decision_id` / `bundle_id` / `record_id`.
