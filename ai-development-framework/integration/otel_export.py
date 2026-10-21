"""ADR 0020 + 0021: optional OTLP/HTTP (JSON) export of control-plane outcomes, for viewing only.

Off unless ADF_OTEL_ENABLED=1. Only allowlisted keys with str/int/bool values leave; a span with
any credential-shaped value is dropped whole. Export runs on a daemon thread and swallows every
error, so it never changes admit/deny. Traces are not evidence: the Evidence Bundle is.
"""
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
import urllib.request


ATTRIBUTES = frozenset({"adf.edge", "adf.agent_type", "adf.skill", "adf.outcome", "adf.reason_code", "adf.has_principal", "adf.act_depth", "adf.decision_id", "adf.bundle_id", "adf.record_id", "adf.task_state", "adf.confirmation", "adf.duration_ms", "http.response.status_code"})
EDGES = frozenset({"claude_read", "codex_bash", "mcp_read"})  # ADR 0021: closed enum for adf.edge
_CREDENTIAL = re.compile(r"eyJ[A-Za-z0-9_-]*\.|bearer|secret|password|private", re.I)


def emit_span(name, attributes, start_ns, end_ns, quiet=False):
    """No-op unless enabled; never raises. `None` values are left out. Returns the sender thread (or
    None) so a short-lived edge can wait for it; `quiet` keeps failures off stderr (hook edges)."""
    if os.environ.get("ADF_OTEL_ENABLED") != "1":
        return None
    try:
        payload = _payload(name, {key: value for key, value in attributes.items() if value is not None}, start_ns, end_ns)
        if payload is not None:
            # ponytail: one thread per span; a batching queue if request rate ever matters.
            thread = threading.Thread(target=_post, args=(payload, quiet), daemon=True)
            thread.start()
            return thread
    except Exception as exc:  # fail open for the product path
        if not quiet:
            sys.stderr.write(f"otel export skipped: {type(exc).__name__}\n")
    return None


def emit_local_read(edge, result, start_ns, hook, agent_type=None):
    """ADR 0021: one span per local-edge decision, built from the adapter result only (never path,
    command or session). A hook exits right after answering, so it waits up to ADF_OTEL_FLUSH_MS."""
    try:
        end_ns = time.time_ns()
        attributes = {"adf.edge": edge, "adf.agent_type": agent_type, "adf.outcome": result.get("outcome"), "adf.reason_code": result.get("reason_code"), "adf.bundle_id": result.get("bundle_id"), "adf.duration_ms": (end_ns - start_ns) // 1_000_000}
        thread = emit_span("adf.local_read.request", attributes, start_ns, end_ns, quiet=hook)
        if thread is not None and hook:
            thread.join(_flush_seconds())
    except Exception:  # the gates turn any exception into a deny; export must never decide
        pass


def _flush_seconds():
    """ADF_OTEL_FLUSH_MS, default 300, capped at 2000; anything else falls back to the default."""
    raw = os.environ.get("ADF_OTEL_FLUSH_MS", "300")
    return min(int(raw), 2000) / 1000 if raw.isascii() and raw.isdecimal() else 0.3


def _payload(name, attributes, start_ns, end_ns):
    """OTLP JSON for one span, or None (fail closed) on any non-allowlisted key or suspect value."""
    service = os.environ.get("ADF_OTEL_SERVICE_NAME", "adf-control-plane")
    if not set(attributes) <= ATTRIBUTES or not all(type(value) in (str, int, bool) for value in attributes.values()):
        return None
    if "adf.edge" in attributes and attributes["adf.edge"] not in EDGES:
        return None
    if any(isinstance(value, str) and _CREDENTIAL.search(value) for value in (name, service, *attributes.values())):
        return None
    status = attributes.get("http.response.status_code", 0)
    span = {"traceId": secrets.token_hex(16), "spanId": secrets.token_hex(8), "name": name, "kind": 2, "startTimeUnixNano": str(start_ns), "endTimeUnixNano": str(end_ns), "attributes": [{"key": key, "value": _value(value)} for key, value in sorted(attributes.items())], "status": {"code": 2 if status >= 500 else 0}}
    resource = {"attributes": [{"key": "service.name", "value": {"stringValue": service}}]}
    return json.dumps({"resourceSpans": [{"resource": resource, "scopeSpans": [{"scope": {"name": "adf.control_plane"}, "spans": [span]}]}]}).encode()


def _value(value):
    if type(value) is bool:
        return {"boolValue": value}
    return {"intValue": str(value)} if type(value) is int else {"stringValue": value}


def _headers(endpoint):
    """ADF_OTEL_EXPORTER_OTLP_HEADERS, OTel format `k=v,k2=v2` (values URL-encoded), e.g. Langfuse
    `Authorization=Basic%20<base64(pk:sk)>`. Credentials only over https or loopback; never logged."""
    raw = os.environ.get("ADF_OTEL_EXPORTER_OTLP_HEADERS", "")
    headers = {key.strip(): urllib.parse.unquote(value.strip()) for key, _, value in (item.partition("=") for item in raw.split(",") if item.strip())}
    if headers and urllib.parse.urlsplit(endpoint).scheme != "https" and urllib.parse.urlsplit(endpoint).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("otlp_headers_need_https")
    return headers


def _post(payload, quiet=False):
    endpoint = os.environ.get("ADF_OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318").rstrip("/")
    try:
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("otlp_endpoint_scheme")
        request = urllib.request.Request(f"{endpoint}/v1/traces", data=payload, headers={**_headers(endpoint), "Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(request, timeout=2).close()
    except Exception as exc:  # collector down = no trace, same answer; type only, never the URL
        if not quiet:
            sys.stderr.write(f"otel export failed: {type(exc).__name__}\n")
