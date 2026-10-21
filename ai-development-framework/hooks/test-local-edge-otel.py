"""ADR 0021: one OTel span per local-edge decision (Claude Read, Codex cat, MCP); never changes it or leaks."""
import contextlib
import importlib.util
import io
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import integration.otel_export as otel
from integration import mcp_read_server

ROOT = Path(__file__).resolve().parent.parent


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


claude = _module("claude_code_read_gate", ROOT / "hooks/claude-code-read-gate.py")
codex = _module("codex_bash_read_gate", ROOT / "hooks/codex-bash-read-gate.py")
pack = _module("effect_security_read_v0", ROOT / "policy-packs/effect-security-read-v0/build.py")
otel_suite = _module("otel_suite", ROOT / "hooks/test-otel-export.py")
Sink, attrs = otel_suite.Sink, otel_suite.attrs
SESSION, SECRET, PUBLIC = "sess-otel-sentinel-1", "AKIA-otel-fake-secret", "public readme for otel"
SENTINEL_DIR = "zzsentineldir"


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


class LocalEdgeOtelTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.repo = base / "repo"; (self.repo / SENTINEL_DIR).mkdir(parents=True); (self.repo / "config").mkdir()
        (self.repo / "README.md").write_text(PUBLIC); (self.repo / "config/.env").write_text(SECRET)
        (self.repo / SENTINEL_DIR / "notes.md").write_text("not allowlisted")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "o@example.invalid"); git(self.repo, "config", "user.name", "o")
        git(self.repo, "add", "-f", "."); git(self.repo, "commit", "-qm", "fixture")
        target, pin = pack.write(pack.build(SESSION, ["README.md"], 64), base / "host-policy.json")
        self.host = {"ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_TRUSTED_REVISION": "HEAD", "ADF_EVIDENCE_DIR": str(base / "evidence"), "ADF_MAX_OUTPUT_BYTES": "64",
                     "ADF_READ_POLICY_FILE": str(target), "ADF_READ_POLICY_SHA256": pin, "ADF_RUN_ID": SESSION}
        self.sink = Sink(); self.addCleanup(self.sink.close)

    def env(self, **extra): return patch.dict(os.environ, {**self.host, **extra}, clear=True)

    def on(self, **extra): return self.env(ADF_OTEL_ENABLED="1", ADF_OTEL_EXPORTER_OTLP_ENDPOINT=self.sink.endpoint, **extra)

    def claude(self, path): return claude.gate({"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": SESSION, "tool_input": {"file_path": str(self.repo / path)}})

    def codex(self, path): return codex.gate({"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": SESSION, "tool_input": {"command": f"cat {self.repo / path}"}})

    def mcp(self, path):
        try: return mcp_read_server.read_snapshot(path)
        except Exception as exc: return f"error:{exc}"

    def decisions(self):
        """allow/deny + reason for each edge; the bundle id is per decision, so it is left out."""
        raw = [self.claude("README.md"), self.claude("config/.env"), self.codex("README.md"), self.codex(f"{SENTINEL_DIR}/notes.md"), self.mcp("README.md"), self.mcp(f"{SENTINEL_DIR}/notes.md")]
        return [re.sub(r" bundle=[0-9a-f]{64}", "", json.dumps(item, sort_keys=True)) for item in raw]

    def test_off_by_default_starts_no_thread(self):
        with self.env(), patch.object(otel.threading, "Thread", side_effect=AssertionError("no thread when disabled")):
            self.assertEqual(len(self.decisions()), 6)
        self.assertEqual(self.sink.bodies, [])

    def test_each_edge_emits_one_redacted_span_before_the_hook_returns(self):
        cases = ((self.claude, "README.md", "claude_read", "delivered", "read_delivered"), (self.claude, "config/.env", "claude_read", "deny", "invalid_scope"),
                 (self.codex, f"{SENTINEL_DIR}/notes.md", "codex_bash", "deny", "scope_not_allowlisted"), (self.mcp, "README.md", "mcp_read", "delivered", "read_delivered"))
        with self.on():
            for call, path, edge, outcome, reason in cases:
                before = len(self.sink.bodies)
                call(path)
                if edge != "mcp_read":  # hooks wait (bounded) for the post: the span is already there
                    self.assertEqual(len(self.sink.bodies), before + 1, edge)
                span = self.sink.span()
                self.assertEqual(span["name"], "adf.local_read.request")
                self.assertEqual({key: value for key, value in attrs(span).items() if key != "adf.duration_ms"},
                                 {"adf.edge": edge, **({"adf.agent_type": "main"} if edge != "mcp_read" else {}), "adf.outcome": outcome, "adf.reason_code": reason, "adf.bundle_id": attrs(span)["adf.bundle_id"]})
        raw = b"".join(self.sink.bodies).decode()
        for forbidden in (SESSION, SENTINEL_DIR, "README", "config", ".env", "cat ", str(self.repo), PUBLIC, SECRET):
            self.assertNotIn(forbidden, raw)

    def test_subagent_identity_reaches_the_span_and_the_journal_but_never_the_bundle(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": SESSION, "agent_id": "af2a1d1014d2e9b6b", "agent_type": "security-reviewer", "tool_input": {"file_path": str(self.repo / "config/.env")}}
        with self.on(): decision = claude.gate(payload)
        self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(attrs(self.sink.span())["adf.agent_type"], "security-reviewer")
        self.assertNotIn("af2a1d1014d2e9b6b", b"".join(self.sink.bodies).decode(), "agent_id is not an attribute")
        evidence = Path(self.host["ADF_EVIDENCE_DIR"])
        started = [json.loads(line) for path in (evidence / "_attempts").glob("*.jsonl") for line in path.read_text().splitlines()][0]
        self.assertEqual(started["payload"], {"principal_sub": "claude:security-reviewer"})
        self.assertNotIn("security-reviewer", "".join(path.read_text() for path in (evidence / SESSION).glob("*.json")), "bundles stay principal-free")
        spans, journals = len(self.sink.bodies), len(list((evidence / "_attempts").glob("*.jsonl")))
        for bad in ("../x", "a" * 121, "", 7, "sec reviewer"):
            with self.subTest(agent_type=bad), self.on():
                denied = claude.gate({**payload, "agent_type": bad})["hookSpecificOutput"]
                self.assertEqual(denied["permissionDecision"], "deny"); self.assertIn("invalid_principal", denied["permissionDecisionReason"])
        self.assertEqual((len(self.sink.bodies), len(list((evidence / "_attempts").glob("*.jsonl")))), (spans, journals), "a malformed principal never reaches the adapter or the exporter")
        with self.on():
            codex_decision = codex.gate({"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": SESSION, "agent_type": "backend-reviewer", "tool_input": {"command": f"cat {self.repo / 'README.md'}"}})
        self.assertEqual(codex_decision, {}); self.assertEqual(attrs(self.sink.span())["adf.agent_type"], "backend-reviewer")

    def test_decisions_are_identical_with_export_off_on_down_or_raising(self):
        with self.env(): baseline = self.decisions()
        down = f"http://127.0.0.1:{otel_suite.closed_port()}"
        for label, context in (("on", self.on()), ("down", self.env(ADF_OTEL_ENABLED="1", ADF_OTEL_EXPORTER_OTLP_ENDPOINT=down))):
            with self.subTest(label), context: self.assertEqual(self.decisions(), baseline)
        with self.on(), patch.object(otel, "emit_span", side_effect=RuntimeError("boom")):
            self.assertEqual(self.decisions(), baseline, "an exporter bug must not become adapter_failed")

    def test_flush_is_bounded_and_hooks_stay_silent_on_export_failure(self):
        blackhole = socket.socket(); blackhole.bind(("127.0.0.1", 0)); blackhole.listen(8); self.addCleanup(blackhole.close)  # accepts, never answers
        stderr = io.StringIO()
        with self.env(ADF_OTEL_ENABLED="1", ADF_OTEL_EXPORTER_OTLP_ENDPOINT=f"http://127.0.0.1:{blackhole.getsockname()[1]}", ADF_OTEL_FLUSH_MS="200"), contextlib.redirect_stderr(stderr):
            started = time.monotonic(); self.claude("README.md"); elapsed = time.monotonic() - started
        self.assertLess(elapsed, 1.5, "the hook must not wait for the 2 s socket timeout")
        down = f"http://127.0.0.1:{otel_suite.closed_port()}"
        with self.env(ADF_OTEL_ENABLED="1", ADF_OTEL_EXPORTER_OTLP_ENDPOINT=down), contextlib.redirect_stderr(stderr):
            self.claude("README.md"); self.codex("README.md")
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(otel._flush_seconds(), 0.3)
        for raw, expected in (("0", 0.0), ("2000", 2.0), ("99999", 2.0), ("-1", 0.3), ("abc", 0.3)):
            with patch.dict(os.environ, {"ADF_OTEL_FLUSH_MS": raw}): self.assertEqual(otel._flush_seconds(), expected, raw)

    def test_edge_is_a_closed_enum(self):
        with self.on():
            otel.emit_local_read("cursor_read", {"outcome": "deny", "reason_code": "x", "bundle_id": None}, time.time_ns(), hook=True)
            otel.emit_local_read("claude_read", {"outcome": "deny", "reason_code": "x", "bundle_id": None}, time.time_ns(), hook=True)
        self.assertEqual(len(self.sink.bodies), 1)
        self.assertEqual(attrs(self.sink.span())["adf.edge"], "claude_read")

    def test_a2a_read_still_emits_exactly_one_span(self):
        suite = otel_suite.suite.A2AGatewayTest("test_happy_path_reads_through_the_pep_and_persists_verifiable_evidence")
        suite.setUp(); self.addCleanup(suite.doCleanups)
        with patch.dict(os.environ, {"ADF_OTEL_ENABLED": "1", "ADF_OTEL_EXPORTER_OTLP_ENDPOINT": self.sink.endpoint}):
            status, _ = suite.call()
            self.assertEqual(self.sink.span()["name"], "adf.a2a.request")
            time.sleep(0.3)  # give a hypothetical second (adapter-level) span time to arrive
        self.assertEqual((status, len(self.sink.bodies)), (200, 1))


if __name__ == "__main__": unittest.main(verbosity=2)
