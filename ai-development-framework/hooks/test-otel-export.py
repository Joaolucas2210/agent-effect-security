"""ADR 0020: OTel export observes A2A outcomes and never changes them or leaks credentials."""
import contextlib
import importlib.util
import io
import json
import os
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

import integration.otel_export as otel


spec = importlib.util.spec_from_file_location("a2a_suite", Path(__file__).with_name("test-a2a-gateway.py"))
suite = importlib.util.module_from_spec(spec); spec.loader.exec_module(suite)


class Sink:
    """A local OTLP/HTTP receiver: collects raw request bodies posted to /v1/traces."""
    def __init__(self):
        self.bodies, self.paths, self.headers, self.arrived = [], [], [], threading.Semaphore(0)
        sink = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                sink.paths.append(self.path); sink.headers.append(self.headers); sink.bodies.append(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200); self.end_headers(); sink.arrived.release()
            def log_message(self, *args): pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"

    def close(self): self.server.shutdown(); self.server.server_close()

    def span(self):
        assert self.arrived.acquire(timeout=5), "no span exported"
        return json.loads(self.bodies[-1])["resourceSpans"][0]["scopeSpans"][0]["spans"][0]


def attrs(span): return {item["key"]: next(iter(item["value"].values())) for item in span["attributes"]}


def closed_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0)); return probe.getsockname()[1]


class OtelExportTest(suite.A2AGatewayTest):
    """Inherits the whole A2A matrix and runs it with export ON and the collector down."""
    def setUp(self):
        super().setUp()
        enabled = patch.dict(os.environ, {"ADF_OTEL_ENABLED": "1", "ADF_OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{closed_port()}"})
        enabled.start(); self.addCleanup(enabled.stop)

    def env(self, **values): return patch.dict(os.environ, values)

    def outcomes(self):
        """401, 403 and 200 delivered, as (status, reason_code)."""
        def reason(status, payload): return status, (payload.get("result") or payload["error"]["data"])["reason_code"]
        return [reason(*self.call(token=None)), reason(*self.call(token=self.token(scope="other:read"))), reason(*self.call())]

    def test_disabled_is_a_no_op(self):
        with self.env(ADF_OTEL_ENABLED="0"), patch.object(otel.threading, "Thread") as thread:
            self.assertEqual(self.outcomes(), [(401, "auth_missing"), (403, "insufficient_scope"), (200, "read_delivered")])
        thread.assert_not_called()

    def test_enabled_spans_carry_ids_and_codes_only(self):
        sink, token = Sink(), self.token()
        self.addCleanup(sink.close)
        with self.env(ADF_OTEL_ENABLED="1", ADF_OTEL_EXPORTER_OTLP_ENDPOINT=sink.endpoint):
            status, payload = self.call(token=token)
            delivered = sink.span()
            self.call(token=None); unauthenticated = sink.span()
        self.assertEqual((status, sink.paths[0], delivered["name"]), (200, "/v1/traces", "adf.a2a.request"))
        audit, seen = payload["result"]["audit"], attrs(delivered)
        self.assertEqual({key: seen[key] for key in ("adf.outcome", "adf.reason_code", "adf.skill", "adf.decision_id", "adf.bundle_id", "adf.record_id", "adf.has_principal")},
                         {"adf.outcome": "delivered", "adf.reason_code": "read_delivered", "adf.skill": "read_workspace_file", "adf.has_principal": True, **{f"adf.{key}": audit[key] for key in ("decision_id", "bundle_id", "record_id")}})
        self.assertEqual((attrs(unauthenticated)["adf.reason_code"], attrs(unauthenticated)["adf.has_principal"]), ("auth_missing", False))
        for span in (delivered, unauthenticated):
            self.assertLessEqual(set(attrs(span)), otel.ATTRIBUTES)
        raw = b"".join(sink.bodies).decode()
        for leaked in (token, "Bearer", "authorization", "raw_token", suite.PUBLIC, suite.APPROVED, "content"):
            self.assertNotIn(leaked, raw)

    def test_input_required_pause_is_visible(self):
        sink = Sink(); self.addCleanup(sink.close)
        with self.env(ADF_OTEL_ENABLED="1", ADF_OTEL_EXPORTER_OTLP_ENDPOINT=sink.endpoint):
            self.call(gateway=self.make(confirm_skills={"read_workspace_file"}))
            seen = attrs(sink.span())
        self.assertEqual((seen["adf.reason_code"], seen["adf.task_state"]), ("input_required", "input-required"))

    def test_export_failure_never_flips_the_decision(self):
        expected = [(401, "auth_missing"), (403, "insufficient_scope"), (200, "read_delivered")]
        with self.env(ADF_OTEL_ENABLED="1"):
            self.assertEqual(self.outcomes(), expected)  # collector down (setUp)
            with patch.object(otel, "_payload", side_effect=RuntimeError("boom")):
                self.assertEqual(self.outcomes(), expected)  # exporter itself raises
            otel._post(b"{}")  # a direct failed post logs and returns
        with self.env(ADF_OTEL_ENABLED="1", ADF_OTEL_EXPORTER_OTLP_ENDPOINT="file:///etc/passwd"), patch.object(otel.urllib.request, "urlopen") as urlopen:
            otel._post(b"{}")
        urlopen.assert_not_called()

    def test_credential_or_unknown_key_drops_the_span(self):
        bad = [{"adf.reason_code": "eyJhbGciOi.eyJzdWIi.sig"}, {"adf.reason_code": "Bearer abc"}, {"authorization": "x"}, {"adf.skill": ["list"]}]
        with self.env(ADF_OTEL_ENABLED="1"), patch.object(otel.threading, "Thread") as thread:
            for attributes in bad:
                otel.emit_span("adf.a2a.request", attributes, 0, 1)
            thread.assert_not_called()
            otel.emit_span("adf.a2a.request", {"adf.reason_code": "allowed", "adf.decision_id": None}, 0, 1)
        thread.assert_called_once()

    def test_otlp_headers_reach_the_sink_and_never_the_logs(self):
        sink, basic = Sink(), "Basic cGstbGYtMTpzay1sZi0x"  # base64("pk-lf-1:sk-lf-1"), Langfuse shape
        self.addCleanup(sink.close)
        stderr = io.StringIO()
        with self.env(ADF_OTEL_ENABLED="1", ADF_OTEL_EXPORTER_OTLP_ENDPOINT=sink.endpoint, ADF_OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic%20cGstbGYtMTpzay1sZi0x, x-extra = a=b"), contextlib.redirect_stderr(stderr):
            self.assertEqual(self.call()[0], 200)
            sink.span()
            for endpoint in ("http://collector.example.invalid:4318", "ftp://127.0.0.1"):
                with self.env(ADF_OTEL_EXPORTER_OTLP_ENDPOINT=endpoint), patch.object(otel.urllib.request, "urlopen") as urlopen:
                    otel._post(b"{}")
                urlopen.assert_not_called()  # a credential never leaves over plain http to a remote host
        self.assertEqual((sink.headers[0]["Authorization"], sink.headers[0]["x-extra"], sink.headers[0]["Content-Type"]), (basic, "a=b", "application/json"))
        self.assertNotIn("cGstbGYt", stderr.getvalue() + b"".join(sink.bodies).decode())
        self.assertEqual(stderr.getvalue().count("ValueError"), 2)


if __name__ == "__main__":
    unittest.main(defaultTest="OtelExportTest")
