"""R-12 / ADR 0037 (Phase 2A): bootstrap and failure behaviour per surface, beyond test-hook-failure-semantics.

Characterisation of what ADF itself returns today; how each *client* interprets it (empty stdout, nonzero exit,
timeout) is not exercised here and stays NOT TESTED until ADR 0037's real-client matrix runs.
  - Claude Read gate, enabled project: policy absent -> demo policy decides (R-10); policy half-configured -> deny.
  - Deny-only gate: import error inside an enabled project -> deny; standalone bad stdin -> deny.
  - Codex registration snippet: missing executable -> no decision, like Claude's.
  - Codex shape (project from payload cwd) with divergent pins -> deny before any gate.
  - Legacy per-repo Codex wrapper with no venv interpreter -> nonzero exit, no decision JSON.
  - MCP read server: missing host env -> tool error; neither MCP server nor A2A gateway consults pins.
Throwaway directories only.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


hook = _module("adf_read_hook_bm", "hooks/adf-read-hook.py")
cli = _module("adf_cli_bm", "integration/cli.py")


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], check=True, capture_output=True)


class BootstrapMatrixTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.repo, self.home = self.base / "repo", self.base / "adf-home"
        self.repo.mkdir(); self.home.mkdir(); (self.repo / "README.md").write_text("public")
        git(self.repo, "init", "-q"); git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")
        clean = {key: value for key, value in os.environ.items() if not key.startswith(("ADF_", "CLAUDE_"))}
        self.env = patch.dict(os.environ, {**clean, "ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo), "ADF_OTEL_ENABLED": "0"}, clear=True)
        self.env.start(); self.addCleanup(self.env.stop)

    def read_payload(self): return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "s-bm", "tool_input": {"file_path": str(self.repo / "README.md")}})

    def decide(self, raw):
        out = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO(raw)), contextlib.redirect_stdout(out):
            self.assertEqual(hook.main(), 0)
        text = out.getvalue().strip()
        return json.loads(text) if text else None

    @staticmethod
    def verdict(decision):
        inner = (decision or {}).get("hookSpecificOutput") or {}
        return inner.get("permissionDecision"), inner.get("permissionDecisionReason", "")

    # --- Claude Read gate: policy missing / invalid -----------------------------------------------------------

    def test_read_with_no_host_policy_is_decided_by_the_demo_policy(self):
        permission, reason = self.verdict(self.decide(self.read_payload()))
        self.assertEqual(permission, "allow", reason)  # R-10: the demo policy applies; the bundle does not say so

    def test_read_with_half_configured_policy_is_a_deny(self):
        os.environ["ADF_READ_POLICY_FILE"] = str(self.base / "missing-policy.json")
        permission, reason = self.verdict(self.decide(self.read_payload()))
        self.assertEqual(permission, "deny"); self.assertIn("host_policy_invalid", reason)

    # --- deny-only gate ---------------------------------------------------------------------------------------

    def test_deny_gate_import_error_in_enabled_project_is_a_deny(self):
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Edit", "session_id": "s-bm", "tool_input": {"file_path": str(self.repo / "README.md")}})
        with patch.object(hook, "_load", side_effect=ImportError("broken deny gate")):
            permission, reason = self.verdict(self.decide(payload))
        self.assertEqual((permission, "adapter_failed" in reason), ("deny", True))

    def test_standalone_deny_gate_with_bad_stdin_is_a_deny(self):
        proc = subprocess.run([sys.executable, str(ROOT / "hooks/adf-deny-gate.py")], input="{not json", capture_output=True, text=True, timeout=60, env=dict(os.environ))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.verdict(json.loads(proc.stdout))[0], "deny")

    # --- Codex --------------------------------------------------------------------------------------------------

    def test_codex_snippet_with_missing_executable_is_no_decision(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.cmd_hook_snippet(["codex"]), 0)
        entry = json.loads(out.getvalue())["hooks"]["PreToolUse"]
        self.assertEqual([item["matcher"] for item in entry], ["^Bash$"])
        command = entry[0]["hooks"][0]["command"].replace(str(Path(sys.executable).parent / "adf"), str(self.base / "missing-adf"))
        self.assertIn('[ -x "$A" ] || exit 0', command)
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo), "session_id": "s", "tool_input": {"command": "cat README.md"}})
        proc = subprocess.run(["sh", "-c", command], input=payload, capture_output=True, text=True, timeout=30)
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_codex_shape_with_divergent_pins_is_a_deny_before_any_gate(self):
        del os.environ["CLAUDE_PROJECT_DIR"]  # Codex: project only from the payload cwd
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo), "session_id": "s-bm", "tool_input": {"command": "cat README.md"}})
        with patch("integration.control_plane_pins.check", return_value=["registration"]):
            permission, reason = self.verdict(self.decide(payload))
        self.assertEqual(permission, "deny"); self.assertIn("control_plane_tampered", reason)

    def test_legacy_codex_wrapper_without_venv_exits_nonzero_with_no_decision(self):
        clone = self.base / "clone"; hooks = clone / "ai-development-framework/hooks"; hooks.mkdir(parents=True)
        shutil.copy2(ROOT / "hooks/codex-bash-read-gate.wrapper.sh", hooks / "codex-bash-read-gate.wrapper.sh")
        proc = subprocess.run(["bash", str(hooks / "codex-bash-read-gate.wrapper.sh")], input="{}", capture_output=True, text=True, timeout=30)
        self.assertNotEqual(proc.returncode, 0); self.assertEqual(proc.stdout, "")  # client interpretation: NOT TESTED

    # --- MCP read server / A2A gateway ------------------------------------------------------------------------

    def test_mcp_read_server_without_host_env_is_a_tool_error(self):
        from mcp.server.mcpserver.exceptions import ToolError
        from integration import mcp_read_server
        with self.assertRaises(ToolError) as caught:
            mcp_read_server.read_snapshot("README.md")
        self.assertIn("host_configuration_invalid", str(caught.exception))

    def test_mcp_server_and_a2a_gateway_do_not_consult_pins(self):
        for relative in ("integration/mcp_read_server.py", "integration/a2a_gateway.py"):
            self.assertNotIn("control_plane_pins", (ROOT / relative).read_text(encoding="utf-8"), relative)


if __name__ == "__main__":
    unittest.main(verbosity=2)
