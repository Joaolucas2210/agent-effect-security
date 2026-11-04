"""ADR 0031 + 0028 1c extension (INC-02): the host registry may declare which registered MCP tools write or reach
the network; once the session attempted a sensitive path, those tools are denied. Reads stay allowed; a clean
session is untouched; the shape is closed.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks/adf-read-hook.py"
sys.path.insert(0, str(ROOT))
from integration import mcp_registry  # noqa: E402


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


def pin(value): return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class McpEffectsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve(); self.home, self.repo = base / "adf-home", base / "proj"
        self.home.mkdir(); (self.repo / "config").mkdir(parents=True); (self.repo / "config/.env").touch(); (self.repo / "README.md").write_text("public")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "-f", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")
        self.registry = {"schema_version": "1.0", "servers": {"github": {"tools": ["get_issue", "create_pull_request", "create_issue"], "effects": {"create_pull_request": "network", "create_issue": "write"}}, "fs": {"tools": ["read_file"]}}}
        self.registry_file = self.home / "mcp-registry.json"; self.registry_file.write_text(json.dumps(self.registry)); self.pin = pin(self.registry)

    def run_hook(self, tool, tool_input=None, session="sess-fx"):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": session, "tool_input": tool_input if tool_input is not None else {"x": 1}}
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home.parent), "ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo), "ADF_MCP_REGISTRY_FILE": str(self.registry_file), "ADF_MCP_REGISTRY_SHA256": self.pin}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"] if result.stdout.strip() else None

    def test_registry_shape_for_effects_is_closed(self):
        mcp_registry.validate(self.registry)
        for bad in ({"get_issue": "read"}, {"nope": "write"}, {"create_issue": "exfil"}, ["create_issue"], {"create_issue": None}):
            with self.subTest(bad):
                reg = json.loads(json.dumps(self.registry)); reg["servers"]["github"]["effects"] = bad
                self.assertRaises(mcp_registry.RegistryInvalid, mcp_registry.validate, reg)

    def test_clean_session_is_untouched(self):
        for tool in ("mcp__github__get_issue", "mcp__github__create_pull_request", "mcp__github__create_issue", "mcp__fs__read_file"):
            with self.subTest(tool): self.assertIsNone(self.run_hook(tool))

    def test_after_a_sensitive_attempt_write_and_network_tools_are_denied_reads_are_not(self):
        self.assertIn("uncovered_read_denied_sensitive", self.run_hook("Grep", {"pattern": "KEY", "path": str(self.repo / "config/.env")}))
        self.assertIn("uncovered_network_denied_after_sensitive_read", self.run_hook("mcp__github__create_pull_request"))
        self.assertIn("uncovered_network_denied_after_sensitive_read", self.run_hook("mcp__github__create_issue"))
        self.assertIsNone(self.run_hook("mcp__github__get_issue"), "a read tool is not an exfiltration channel")
        self.assertIsNone(self.run_hook("mcp__fs__read_file"), "a server without effects keeps names-only behaviour")
        self.assertIsNone(self.run_hook("mcp__github__create_pull_request", session="sess-clean"), "other sessions are clean")
        self.assertIn("mcp_tool_not_registered", self.run_hook("mcp__github__delete_repo"), "unregistered stays unregistered")
        journals = sorted((self.home / "evidence").rglob("_attempts/*.jsonl")); text = "".join(p.read_text() for p in journals)
        self.assertEqual(text.count("uncovered_network_denied_after_sensitive_read"), 2); self.assertNotIn("config/.env", text)


if __name__ == "__main__": unittest.main(verbosity=2)
