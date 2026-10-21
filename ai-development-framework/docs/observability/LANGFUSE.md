# Runbook: two screens — agent (Langfuse) + control (ADF)

**English** · [Português (Brasil)](LANGFUSE.pt-BR.md)

For design partners. Langfuse shows **what the agent did**; ADF decides **what it may
do** and keeps the proof. They are different screens with different questions, and neither replaces the
other. Base: [ADR 0020](../architecture-decision-records/0020-control-plane-otel-export.md).

```text
Agent (Claude Code / Codex / A2A peer)
  ├─ native agent traces ───────────────────► Langfuse   "what it did": turns, tools, graph
  └─ request ─► ADF A2A edge (AuthN → scope → PDP → PEP → effect/deny)
                  ├─ span adf.a2a.request ──► Langfuse or Jaeger   (ids + reason_code, redacted)
                  └─ A2AEvidenceRecord + EvidenceBundle ─► evidence/_a2a/ + evidence/<run>/
                                                            source of truth: verify_record
```

- **Langfuse ≠ authorization.** Nothing reads spans to decide; turning the export on or off does not change
  admit/deny (the whole A2A suite runs with export on and the collector down).
- **Export ≠ audit.** The span can be missing and is not signed. The audit is the Evidence Bundle.
- **Agent hooks are telemetry, not enforcement.** What Claude Code/Codex send to
  Langfuse describes the agent; the ADF gate is what blocks.

## 1. Local Jaeger (baseline)

```bash
docker compose -f docs/observability/docker-compose.otel.yml up -d     # UI at http://127.0.0.1:16686
export ADF_OTEL_ENABLED=1 ADF_OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
python3 -m integration.a2a_gateway serve &      # + A2A pilot env (CONTROL_PLANE.md § A2A edge)
```

Run the 401/403/200 matrix from [CONTROL_PLANE.md § Observability](../CONTROL_PLANE.md#observability-otel-adr-0020).

## 2. Langfuse as an OTLP sink (cloud or self-host)

Same exporter, same allowlist; only the destination and one header change. The exporter appends
`/v1/traces` to the endpoint.

```bash
export ADF_OTEL_ENABLED=1
export ADF_OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel   # EU
# US: https://us.cloud.langfuse.com/api/public/otel · self-host: https://<host>/api/public/otel
read -rs LF_SK                                     # sk-lf-…, without echoing or going into history
AUTH="$(printf '%s:%s' "pk-lf-…" "$LF_SK" | base64 -w0)"; unset LF_SK
export ADF_OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic%20$AUTH"
python3 -m integration.a2a_gateway serve &
```

`ADF_OTEL_EXPORTER_OTLP_HEADERS` follows the OTel `k=v,k2=v2` format (URL-encoded values; the space
in `Basic <b64>` becomes `%20`). Rules:

- Headers are sent only over `https://` or to loopback (`127.0.0.1`/`localhost`/`::1`, e.g. a local
  self-hosted Langfuse). `http://` to a remote host with headers → send refused, one line
  `otel export failed: ValueError` on stderr, same A2A response.
- The value is never logged and never goes into the span or the evidence; an error reports only the type.
- Wrong key / Langfuse down → `otel export failed: HTTPError|URLError`, same response.

In Langfuse: **Tracing** → filter by name `adf.a2a.request`; the `adf.*` attributes appear in
metadata. Service: `adf-control-plane` (or `ADF_OTEL_SERVICE_NAME`).

<a id="3-correlação-span--evidência--verificação"></a>
## 3. Correlation: span → evidence → verification

1. In the span (Jaeger or Langfuse), copy `adf.record_id`, `adf.bundle_id`, `adf.decision_id`.
2. Record: `$ADF_EVIDENCE_DIR/_a2a/<record_id>.json`. Bundle: `$ADF_EVIDENCE_DIR/*/<bundle_id>.json`
   (without `ADF_EVIDENCE_DIR`, the root is `docs/observability/evidence`).
3. Verify offline:

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

`True` = what the span showed is what the edge recorded, and the bundle (`verify_offline`) checks out. A 401
has no record (no identity); a 403 has a record without a bundle.

## 4. The agent's own traces in the same Langfuse project

Use the vendor's integration; ADF does not reimplement agent hooks. See
[Langfuse — integrations](https://langfuse.com/integrations),
[Claude Code — monitoring](https://docs.claude.com/en/docs/claude-code/monitoring-usage) and the
`[otel]` section of the Codex configuration.

Residual: what the agent sends (prompts, file contents) depends on the privacy settings
**of the agent's integration**. ADF spans remain redacted by the ADR 0020 allowlist
and never carry a token, `sub`, `path` or content. The local gate (`local_read`) does not
emit spans yet — only the A2A edge appears on the control screen.
