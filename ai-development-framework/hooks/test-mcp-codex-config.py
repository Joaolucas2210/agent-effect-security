"""ADR 0031 follow-up: Codex `config.toml` MCP definitions are read for offline drift (`adf doctor`), not per call.

Codex never sends MCP calls to the PreToolUse hook, so a Claude-origin call is judged against Claude's scopes
only; Codex drift is a doctor finding. Python 3.10 uses the `tomli` backport; no parser -> unreadable, never ok.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks/adf-read-hook.py"
sys.path.insert(0, str(ROOT))
from integration import mcp_registry  # noqa: E402


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


CODEX_OK = '''
model = "o3"
[mcp_servers.github]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = { GITHUB_TOKEN = "secret-value" }

[mcp_servers.other]
command = "node"
args = ["srv.js"]
[mcp_servers.other.env]
A = "1"
'''


class McpCodexConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.user_home, self.repo = base / "home", base / "proj"; self.home = self.user_home / ".adf"
        (self.user_home / ".codex").mkdir(parents=True); self.home.mkdir(); self.repo.mkdir(); (self.repo / "README.md").write_text("public")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")
        self.definition = {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env_keys": ["GITHUB_TOKEN"]}
        fresh = {"tools_sha256": "0" * 64, "probed_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}  # probe age is a separate doctor finding
        self.registry = {"schema_version": "1.0", "servers": {"github": {"tools": ["get_issue"], "definition": self.definition, **fresh}, "other": {"tools": ["x"], "definition": {"command": "node", "args": ["srv.js"], "env_keys": ["A"]}, **fresh}}}
        self.registry_file = self.home / "mcp-registry.json"; self.registry_file.write_text(json.dumps(self.registry)); self.pin = mcp_registry.pin(self.registry)
        (self.user_home / ".codex/config.toml").write_text(CODEX_OK)
        (self.user_home / ".claude.json").write_text(json.dumps({"mcpServers": {"github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "t"}}}}))

    def test_codex_definitions_are_parsed_from_both_table_forms(self):
        self.assertEqual(mcp_registry.client_definitions("github", self.repo, self.user_home, client="codex"), [self.definition])
        self.assertEqual(mcp_registry.client_definitions("other", self.repo, self.user_home, client="codex"), [{"command": "node", "args": ["srv.js"], "env_keys": ["A"]}])
        self.assertEqual(mcp_registry.client_definitions("absent", self.repo, self.user_home, client="codex"), [])
        (self.repo / ".codex").mkdir(); (self.repo / ".codex/config.toml").write_text('[mcp_servers.github]\ncommand = "npx"\nargs = ["-y", "evil"]\n')
        self.assertEqual(len(mcp_registry.client_definitions("github", self.repo, self.user_home, client="codex")), 2, "project-level .codex/config.toml is a second scope")
        (self.user_home / ".codex/config.toml").write_text("this = = not toml")
        self.assertIsNone(mcp_registry.client_definitions("github", self.repo, self.user_home, client="codex"), "unreadable -> None, never 'absent'")

    def test_without_a_toml_parser_codex_config_is_unreadable_not_ok(self):
        with patch.object(mcp_registry, "_toml_loads", None):
            self.assertIsNone(mcp_registry.client_definitions("github", self.repo, self.user_home, client="codex"))
            self.assertEqual(mcp_registry.drift(self.registry, self.repo, self.user_home)["github"]["codex"], "unreadable")

    def test_drift_report_covers_both_clients(self):
        report = mcp_registry.drift(self.registry, self.repo, self.user_home)
        self.assertEqual(report["github"], {"claude": "ok", "codex": "ok"})
        self.assertEqual(report["other"], {"claude": "absent", "codex": "ok"})
        (self.user_home / ".codex/config.toml").write_text(CODEX_OK.replace('"-y", "@modelcontextprotocol/server-github"', '"-y", "evil"'))
        self.assertEqual(mcp_registry.drift(self.registry, self.repo, self.user_home)["github"]["codex"], "changed")
        self.assertEqual(mcp_registry.drift({"schema_version": "1.0", "servers": {"plain": {"tools": ["x"]}}}, self.repo, self.user_home), {}, "no definition pinned: nothing to compare")

    def test_claude_call_is_not_judged_by_codex_config(self):
        (self.user_home / ".codex/config.toml").write_text(CODEX_OK.replace('"-y", "@modelcontextprotocol/server-github"', '"-y", "evil"'))
        payload = {"hook_event_name": "PreToolUse", "tool_name": "mcp__github__get_issue", "session_id": "sess-codex", "tool_input": {}}
        env = {"PATH": os.environ["PATH"], "HOME": str(self.user_home), "ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo), "ADF_MCP_REGISTRY_FILE": str(self.registry_file), "ADF_MCP_REGISTRY_SHA256": self.pin}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, ""), "Claude scopes match: Codex drift is a doctor finding, not a deny of Claude's call")

    def test_doctor_reports_mcp_drift(self):
        env = {**os.environ, "HOME": str(self.user_home), "ADF_HOME": str(self.home), "ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_MCP_REGISTRY_FILE": str(self.registry_file), "ADF_MCP_REGISTRY_SHA256": self.pin}
        def doctor(*args):
            proc = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))", str(ROOT), "doctor", *args], capture_output=True, text=True, env=env)
            return proc.returncode, proc.stdout + proc.stderr
        self.assertEqual(doctor("--pin")[0], 0)
        code, out = doctor(); self.assertEqual(code, 0, out); self.assertIn("mcp github: claude=ok codex=ok", out)
        (self.user_home / ".codex/config.toml").write_text(CODEX_OK.replace('"npx"', '"node"'))
        code, out = doctor(); self.assertEqual(code, 1, out); self.assertIn("codex=changed", out)
        (self.user_home / ".codex/config.toml").write_text("= broken")
        code, out = doctor(); self.assertEqual(code, 1, out); self.assertIn("codex=unreadable", out)


if __name__ == "__main__": unittest.main(verbosity=2)
