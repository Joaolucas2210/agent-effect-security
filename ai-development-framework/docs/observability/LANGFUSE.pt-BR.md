# Runbook: duas telas — agente (Langfuse) + controle (ADF)

[English](LANGFUSE.md) · **Português (Brasil)**

Para design partners. O Langfuse mostra **o que o agente fez**; o ADF decide **o que ele pode
fazer** e guarda a prova. São telas diferentes com perguntas diferentes, e nenhuma substitui a
outra. Base: [ADR 0020](../architecture-decision-records/0020-control-plane-otel-export.md).

```text
Agente (Claude Code / Codex / peer A2A)
  ├─ traces nativos do agente ──────────────► Langfuse   "o que fez": turnos, tools, grafo
  └─ request ─► borda A2A do ADF (AuthN → scope → PDP → PEP → efeito/deny)
                  ├─ span adf.a2a.request ──► Langfuse ou Jaeger   (ids + reason_code, redigido)
                  └─ A2AEvidenceRecord + EvidenceBundle ─► evidence/_a2a/ + evidence/<run>/
                                                            fonte de verdade: verify_record
```

- **Langfuse ≠ autorização.** Nada lê spans para decidir; ligar ou desligar o export não muda
  admit/deny (a suíte A2A inteira roda com export ligado e collector fora).
- **Export ≠ auditoria.** O span pode faltar e não é assinado. Auditoria é o Evidence Bundle.
- **Hooks de agente são telemetria, não enforcement.** O que o Claude Code/Codex mandam para o
  Langfuse descreve o agente; quem barra é o gate do ADF.

## 1. Jaeger local (baseline)

```bash
docker compose -f docs/observability/docker-compose.otel.yml up -d     # UI em http://127.0.0.1:16686
export ADF_OTEL_ENABLED=1 ADF_OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
python3 -m integration.a2a_gateway serve &      # + env do piloto A2A (CONTROL_PLANE.md § Borda A2A)
```

Rode a matriz 401/403/200 de [CONTROL_PLANE.md § Observabilidade](../CONTROL_PLANE.pt-BR.md#observabilidade-otel-adr-0020).

## 2. Langfuse como sink OTLP (cloud ou self-host)

Mesmo exporter, mesma allowlist; só muda o destino e um header. O exporter acrescenta
`/v1/traces` ao endpoint.

```bash
export ADF_OTEL_ENABLED=1
export ADF_OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel   # EU
# US: https://us.cloud.langfuse.com/api/public/otel · self-host: https://<host>/api/public/otel
read -rs LF_SK                                     # sk-lf-…, sem ecoar nem ir para o histórico
AUTH="$(printf '%s:%s' "pk-lf-…" "$LF_SK" | base64 -w0)"; unset LF_SK
export ADF_OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic%20$AUTH"
python3 -m integration.a2a_gateway serve &
```

`ADF_OTEL_EXPORTER_OTLP_HEADERS` segue o formato OTel `k=v,k2=v2` (valores URL-encoded; o espaço
de `Basic <b64>` vira `%20`). Regras:

- Headers só saem por `https://` ou para loopback (`127.0.0.1`/`localhost`/`::1`, p.ex. Langfuse
  self-host local). `http://` para host remoto com headers → envio recusado, uma linha
  `otel export failed: ValueError` em stderr, mesma resposta A2A.
- O valor nunca é logado nem vai para o span ou para a evidência; erro reporta só o tipo.
- Chave errada / Langfuse fora → `otel export failed: HTTPError|URLError`, mesma resposta.

No Langfuse: **Tracing** → filtre por nome `adf.a2a.request`; os atributos `adf.*` aparecem em
metadata. Service: `adf-control-plane` (ou `ADF_OTEL_SERVICE_NAME`).

## 3. Correlação: span → evidência → verificação

1. No span (Jaeger ou Langfuse) copie `adf.record_id`, `adf.bundle_id`, `adf.decision_id`.
2. Record: `$ADF_EVIDENCE_DIR/_a2a/<record_id>.json`. Bundle: `$ADF_EVIDENCE_DIR/*/<bundle_id>.json`
   (sem `ADF_EVIDENCE_DIR`, a raiz é `docs/observability/evidence`).
3. Verifique offline:

```bash
python3 - "$ADF_EVIDENCE_DIR" <record_id> <<'PY'
import json, sys
from pathlib import Path
import integration.a2a_gateway as g, integration.local_read_adapter as a
ev, rid = Path(sys.argv[1]), sys.argv[2]
rec = json.loads((ev / "_a2a" / f"{rid}.json").read_text())
bundle = next(ev.glob(f"*/{rec['bundle_id']}.json"), None) if rec["bundle_id"] else None
print(g.verify_record(rec, bundle and json.loads(bundle.read_text()), a.schemas()))
PY
```

`True` = o que o span mostrou é o que a borda registrou e o bundle (`verify_offline`) fecha. 401
não tem record (sem identidade); 403 tem record sem bundle.

## 4. Traces do próprio agente no mesmo projeto Langfuse

Use a integração do fornecedor; o ADF não reimplementa hooks de agente. Ver
[Langfuse — integrações](https://langfuse.com/integrations),
[Claude Code — monitoring](https://docs.claude.com/en/docs/claude-code/monitoring-usage) e a
seção `[otel]` da configuração do Codex.

Residual: o que o agente manda (prompts, conteúdo de arquivos) depende das configurações de
privacidade **da integração do agente**. Os spans do ADF continuam redigidos pela allowlist do
ADR 0020 e nunca carregam token, `sub`, `path` ou conteúdo. O gate local (`local_read`) ainda
não emite span — só a borda A2A aparece na tela de controle.
