"""ADR 0031 slice 1: MCP calls are denied unless server and tool names are in the host-pinned registry.

Knowledge-base cases: INC-05 (repo-shipped MCP config), INC-11 (Codex loads untrusted MCP config).
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
GATE = ROOT / "hooks/adf-deny-gate.py"


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


def pin(value): return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class McpRegistryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.home, self.repo = base / "adf-home", base / "proj"
        self.home.mkdir(); self.repo.mkdir(); (self.repo / "README.md").write_text("public")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")
        self.registry = {"schema_version": "1.0", "servers": {"github": {"tools": ["get_issue", "list_pull_requests"]}}}
        self.registry_file = self.home / "mcp-registry.json"; self.registry_file.write_text(json.dumps(self.registry))
        self.pin = pin(self.registry)

    def run_hook(self, tool, tool_input=None, **env):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "sess-mcp", "tool_input": tool_input if tool_input is not None else {"x": 1}}
        base_env = {"PATH": os.environ["PATH"], "HOME": str(self.home.parent), "ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo), **env}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=base_env, timeout=120)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def pinned(self, **env): return {"ADF_MCP_REGISTRY_FILE": str(self.registry_file), "ADF_MCP_REGISTRY_SHA256": self.pin, **env}

    def deny(self, tool, reason, **env):
        decision = self.run_hook(tool, **env)
        self.assertIsNotNone(decision, f"{tool} should be denied"); self.assertEqual(decision["permissionDecision"], "deny"); self.assertIn(reason, decision["permissionDecisionReason"])

    def test_without_registry_mcp_calls_are_not_adfs_call(self):
        self.assertIsNone(self.run_hook("mcp__github__get_issue"))
        self.assertIsNone(self.run_hook("mcp__evil__exfiltrate"), "opt-in: no registry configured, no decision (ADR 0011 pattern)")

    def test_partial_or_wrong_pin_denies_everything(self):
        self.deny("mcp__github__get_issue", "mcp_registry_invalid", ADF_MCP_REGISTRY_FILE=str(self.registry_file))
        self.deny("mcp__github__get_issue", "mcp_registry_invalid", ADF_MCP_REGISTRY_SHA256=self.pin)
        self.deny("mcp__github__get_issue", "mcp_registry_invalid", **self.pinned(ADF_MCP_REGISTRY_SHA256="0" * 64))
        self.registry_file.write_text(json.dumps({**self.registry, "servers": {**self.registry["servers"], "evil": {"tools": ["x"]}}}))
        self.deny("mcp__github__get_issue", "mcp_registry_invalid", **self.pinned())  # swapped file, old pin: fail closed
        self.registry_file.write_text("{not json"); self.deny("mcp__github__get_issue", "mcp_registry_invalid", **self.pinned())

    def test_registered_names_pass_unregistered_deny(self):
        self.assertIsNone(self.run_hook("mcp__github__get_issue", **self.pinned()))
        self.assertIsNone(self.run_hook("mcp__github__list_pull_requests", **self.pinned()))
        self.deny("mcp__github__create_pull_request", "mcp_tool_not_registered", **self.pinned())
        self.deny("mcp__supabase__execute_sql", "mcp_server_not_registered", **self.pinned())
        self.deny("mcp__GitHub__get_issue", "mcp_server_not_registered", **self.pinned())  # exact match, no case folding
        for name in ("mcp__", "mcp__github", "mcp__github__", "mcp____get_issue", "mcp__git hub__x"):
            with self.subTest(name): self.deny(name, "mcp_tool_name_invalid", **self.pinned())

    def test_registry_shape_is_closed(self):
        for bad in ({"schema_version": "2.0", "servers": {}}, {"servers": {}}, {"schema_version": "1.0", "servers": {"a": {"tools": "x"}}}, {"schema_version": "1.0", "servers": {"a": {"tools": ["x"], "command": "node"}}}, {"schema_version": "1.0", "servers": [], "extra": 1}):
            self.registry_file.write_text(json.dumps(bad))
            with self.subTest(bad): self.deny("mcp__a__x", "mcp_registry_invalid", **self.pinned(ADF_MCP_REGISTRY_SHA256=pin(bad)))

    def test_other_tools_untouched_and_nothing_persisted(self):
        self.assertIsNone(self.run_hook("Grep", {"pattern": "x", "path": str(self.repo / "README.md")}, **self.pinned()))
        self.assertEqual([p for p in (self.home / "evidence").rglob("*") if p.is_file()] if (self.home / "evidence").exists() else [], [], "a pass-through persists nothing")

    def test_cli_prints_the_pin(self):
        proc = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))", str(ROOT), "mcp", "pin", str(self.registry_file)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr); self.assertIn(self.pin, proc.stdout)
        self.registry_file.write_text(json.dumps({"schema_version": "1.0", "servers": {"a": {"tools": ["x"], "command": "node"}}}))
        proc = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))", str(ROOT), "mcp", "pin", str(self.registry_file)], capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0, "the pin command refuses a registry the gate would refuse")


if __name__ == "__main__": unittest.main(verbosity=2)
