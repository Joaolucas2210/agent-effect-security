"""ADR 0021 extension for the deny-only gate (pilot: latency p95 was `na`): one `adf.local_read.request` span per
deny-gate decision with `adf.edge=deny_gate`, `adf.tool`, outcome `deny` or `no_decision`, the reason code and
`adf.duration_ms`; never a path, command, URL or session id. The pre-gate tamper deny is spanned too.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import integration.otel_export as otel  # noqa: E402


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


otel_suite = _module("otel_suite", ROOT / "hooks/test-otel-export.py")
Sink, attrs = otel_suite.Sink, otel_suite.attrs
gate = _module("adf_deny_gate", ROOT / "hooks/adf-deny-gate.py")
hook = _module("adf_read_hook", ROOT / "hooks/adf-read-hook.py")
SENTINEL = "zzsentinelpath"


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def spans(sink, n):
    """The last n exported spans, in arrival order (Sink.span() only returns the latest)."""
    for _ in range(n):
        assert sink.arrived.acquire(timeout=5), "no span exported"
    return [json.loads(body)["resourceSpans"][0]["scopeSpans"][0]["spans"][0] for body in sink.bodies[-n:]]


class DenyGateOtelTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve(); self.repo = base / "repo"; self.home = base / "adf-home"
        (self.repo / "config").mkdir(parents=True); (self.repo / SENTINEL).mkdir(); self.home.mkdir()
        (self.repo / "README.md").write_text("public"); (self.repo / "config/.env").touch(); (self.repo / SENTINEL / "x.py").touch()
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "o@example.invalid"); git(self.repo, "config", "user.name", "o"); git(self.repo, "add", "-f", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")
        self.sink = Sink(); self.addCleanup(self.sink.close)
        self.base_env = {"HOME": str(base), "ADF_HOME": str(self.home), "ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_EVIDENCE_DIR": str(self.home / "evidence" / "p" / "d"), "CLAUDE_PROJECT_DIR": str(self.repo)}

    def on(self, **extra): return patch.dict(os.environ, {**self.base_env, "ADF_OTEL_ENABLED": "1", "ADF_OTEL_EXPORTER_OTLP_ENDPOINT": self.sink.endpoint, **extra}, clear=True)

    def payload(self, tool, tool_input, **extra):
        return {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "sess-otel-deny-sentinel", "tool_input": tool_input, **extra}

    def test_deny_and_pass_through_each_emit_one_redacted_span(self):
        with self.on():
            denied = gate.gate(self.payload("Edit", {"file_path": str(self.repo / "config/.env"), "old_string": "a", "new_string": "b"}, agent_type="worker"))
            passed = gate.gate(self.payload("Grep", {"pattern": "x", "path": str(self.repo / SENTINEL)}))
        self.assertIsNotNone(denied); self.assertIsNone(passed)
        exported = spans(self.sink, 2)
        by_tool = {attrs(s)["adf.tool"]: attrs(s) for s in exported}
        self.assertEqual(by_tool["Edit"]["adf.edge"], "deny_gate"); self.assertEqual((by_tool["Edit"]["adf.outcome"], by_tool["Edit"]["adf.reason_code"], by_tool["Edit"]["adf.agent_type"]), ("deny", "uncovered_write_denied_sensitive", "worker"))
        self.assertEqual((by_tool["Grep"]["adf.outcome"], by_tool["Grep"].get("adf.reason_code")), ("no_decision", None))
        for span in exported:
            self.assertIn("adf.duration_ms", attrs(span)); self.assertTrue(str(attrs(span)["adf.duration_ms"]).isdigit(), "OTLP JSON carries intValue as a string")
            text = json.dumps(span); self.assertNotIn(SENTINEL, text); self.assertNotIn("config/.env", text); self.assertNotIn("sess-otel-deny-sentinel", text); self.assertNotIn(str(self.repo), text)

    def test_network_and_mcp_denies_carry_the_tool_name_only(self):
        with self.on(ADF_MCP_REGISTRY_FILE=str(self.home / "r.json"), ADF_MCP_REGISTRY_SHA256="0" * 64):
            gate.gate(self.payload("mcp__evil__exfil", {"data": "zzsecretvalue"}))
            gate.gate(self.payload("WebFetch", {"url": "https://zzsentineldomain.invalid/q?x=1"}))
        for raw in spans(self.sink, 2):
            span = attrs(raw)
            self.assertIn(span["adf.tool"], ("mcp__evil__exfil", "WebFetch")); self.assertEqual(span["adf.outcome"], "deny" if span["adf.tool"].startswith("mcp") else "no_decision")
            self.assertNotIn("zzsentineldomain", json.dumps(span)); self.assertNotIn("zzsecretvalue", json.dumps(span))

    def test_tamper_deny_is_spanned_from_the_dispatcher(self):
        with self.on():
            from integration.control_plane_pins import snapshot, write_manifest
            write_manifest(self.home / "pins.json", snapshot(ROOT, self.home))
            (self.home / "enabled-projects").write_text(f"{self.repo}\n/tmp/zz\n")
            decision = hook.decide(json.dumps(self.payload("Read", {"file_path": str(self.repo / "README.md")})))
        self.assertIn("control_plane_tampered", decision["hookSpecificOutput"]["permissionDecisionReason"])
        span = attrs(self.sink.span()); self.assertEqual((span["adf.edge"], span["adf.tool"], span["adf.outcome"], span["adf.reason_code"]), ("deny_gate", "Read", "deny", "control_plane_tampered"))
        self.assertNotIn("/tmp/zz", json.dumps(span))

    def test_off_by_default_and_exporter_still_rejects_unknown_edges(self):
        with patch.dict(os.environ, {**self.base_env, "ADF_OTEL_EXPORTER_OTLP_ENDPOINT": self.sink.endpoint}, clear=True):
            gate.gate(self.payload("Edit", {"file_path": str(self.repo / "config/.env"), "old_string": "a", "new_string": "b"}))
        self.assertFalse(self.sink.arrived.acquire(timeout=0.5), "off by default: nothing exported")
        with self.on():
            self.assertIsNone(otel.emit_span("adf.local_read.request", {"adf.edge": "not_an_edge", "adf.outcome": "deny"}, time.time_ns(), time.time_ns()))
            self.assertIsNone(otel.emit_span("adf.local_read.request", {"adf.edge": "deny_gate", "adf.tool_input": "leak"}, time.time_ns(), time.time_ns()), "attribute allowlist stays closed")


if __name__ == "__main__": unittest.main(verbosity=2)
