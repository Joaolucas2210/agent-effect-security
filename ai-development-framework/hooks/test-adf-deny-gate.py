"""ADR 0028 slice 1a: deny-only gate for Grep/Glob/Edit/Write/MultiEdit/NotebookEdit; path only, never content.

Knowledge-base cases: INC-01 (rules file), INC-05 (.mcp.json), INC-08 (.vscode/settings.json auto-approve).
"""
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


class DenyGateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.home, self.repo = base / "adf-home", base / "proj"
        for path in (self.repo / "config", self.repo / "secrets", self.repo / "src", self.repo / ".claude", self.home): path.mkdir(parents=True)
        (self.repo / "README.md").write_text("public"); (self.repo / "config/.env").touch(); (self.repo / "secrets/token").touch()  # paths matter, content never does
        (self.repo / "src/app.py").write_text("print(1)\n"); (self.repo / ".claude/settings.json").write_text("{}"); (self.repo / "CLAUDE.md").write_text("# rules")
        os.symlink(self.repo / "config/.env", self.repo / "link")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m")
        git(self.repo, "add", "-f", "."); git(self.repo, "commit", "-qm", "fixture")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")

    def run_hook(self, tool, tool_input, enabled=True):
        """As Claude Code runs it: fresh process, JSON on stdin, CLAUDE_PROJECT_DIR from the host."""
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "sess-1a", "tool_input": tool_input}
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home.parent), "ADF_HOME": str(self.home if enabled else self.home / "none"), "CLAUDE_PROJECT_DIR": str(self.repo)}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def deny(self, tool, tool_input, reason):
        decision = self.run_hook(tool, tool_input)
        self.assertIsNotNone(decision, f"{tool} {tool_input} should be denied")
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn(reason, decision["permissionDecisionReason"])

    def path(self, rel): return str(self.repo / rel)

    def test_gate_file_is_the_registered_edge(self):
        self.assertTrue(GATE.exists(), "hooks/adf-deny-gate.py")

    def test_not_enabled_never_decides(self):
        self.assertIsNone(self.run_hook("Edit", {"file_path": self.path("config/.env"), "old_string": "a", "new_string": "b"}, enabled=False))
        self.assertIsNone(self.run_hook("Grep", {"pattern": "AKIA", "path": self.path("config/.env")}, enabled=False))

    def test_read_equivalents_deny_sensitive_paths_only(self):
        self.deny("Grep", {"pattern": "AKIA", "path": self.path("config/.env")}, "uncovered_read_denied_sensitive")
        self.deny("Grep", {"pattern": "x", "path": self.path("secrets")}, "uncovered_read_denied_sensitive")
        self.deny("Glob", {"pattern": "*", "path": self.path("secrets")}, "uncovered_read_denied_sensitive")
        self.deny("Grep", {"pattern": "x", "path": self.path("link")}, "uncovered_read_denied_sensitive")  # symlink to .env
        self.deny("Grep", {"pattern": "x", "path": self.path("src/../config/.env")}, "uncovered_read_denied_sensitive")
        self.assertIsNone(self.run_hook("Grep", {"pattern": "AKIA"}), "no path: whole-root search is a documented residual, not a deny")
        self.assertIsNone(self.run_hook("Grep", {"pattern": "x", "path": self.path("src")}))
        self.assertIsNone(self.run_hook("Glob", {"pattern": "**/*.py", "path": self.path("src")}))
        self.assertIsNone(self.run_hook("Grep", {"pattern": "x", "path": self.path("CLAUDE.md")}), "reading agent config is not a write; only the sensitive list applies")

    def test_writes_deny_sensitive_and_agent_config_paths(self):
        edit = {"old_string": "a", "new_string": "b"}
        self.deny("Edit", {"file_path": self.path(".vscode/settings.json"), **edit}, "uncovered_write_denied_agent_config")  # INC-08
        self.deny("Write", {"file_path": self.path(".vscode/settings.json"), "content": "{}"}, "uncovered_write_denied_agent_config")
        self.deny("Edit", {"file_path": self.path(".claude/settings.json"), **edit}, "uncovered_write_denied_agent_config")
        self.deny("Write", {"file_path": self.path(".cursor/rules/x.mdc"), "content": ""}, "uncovered_write_denied_agent_config")  # INC-01
        self.deny("MultiEdit", {"file_path": self.path(".mcp.json"), "edits": []}, "uncovered_write_denied_agent_config")  # INC-05
        self.deny("Edit", {"file_path": self.path("CLAUDE.md"), **edit}, "uncovered_write_denied_agent_config")
        self.deny("Edit", {"file_path": self.path("docs/AGENTS.md"), **edit}, "uncovered_write_denied_agent_config")
        self.deny("Write", {"file_path": self.path(".github/workflows/ci.yml"), "content": ""}, "uncovered_write_denied_agent_config")
        self.deny("NotebookEdit", {"notebook_path": self.path(".codex/n.ipynb"), "new_source": ""}, "uncovered_write_denied_agent_config")
        self.deny("Write", {"file_path": self.path("config/.env"), "content": "x"}, "uncovered_write_denied_sensitive")
        self.deny("Edit", {"file_path": self.path("link"), **edit}, "uncovered_write_denied_sensitive")
        self.deny("Write", {"file_path": self.path("secrets/new.pem"), "content": ""}, "uncovered_write_denied_sensitive")
        self.assertIsNone(self.run_hook("Edit", {"file_path": self.path("src/app.py"), **edit}))
        self.assertIsNone(self.run_hook("Write", {"file_path": self.path("docs/new.md"), "content": ""}))

    def test_adf_home_is_agent_config_even_outside_the_root(self):
        self.deny("Edit", {"file_path": str(self.home / "enabled-projects"), "old_string": "a", "new_string": ""}, "uncovered_write_denied_agent_config")
        self.deny("Write", {"file_path": str(self.home / "policy.json"), "content": "{}"}, "uncovered_write_denied_agent_config")
        self.assertIsNone(self.run_hook("Write", {"file_path": str(Path(self.temp.name) / "scratch.txt"), "content": ""}), "other paths outside the root are not ADF's call")

    def test_malformed_input_fails_closed(self):
        self.deny("Edit", {"old_string": "a", "new_string": "b"}, "unexpected_tool_input")
        self.deny("Write", {"file_path": 7}, "unexpected_tool_input")
        self.deny("Grep", "not a dict", "unexpected_tool_input")
        self.deny("Edit", {"file_path": self.path("src/a\x00.py")}, "unexpected_tool_input")

    def test_gate_never_reads_content_or_writes_evidence(self):
        self.run_hook("Edit", {"file_path": self.path("config/.env"), "old_string": "a", "new_string": "b"})
        self.assertFalse((self.home / "evidence").exists(), "slice 1a: deny without bundle, nothing persisted")
        self.assertEqual(git(self.repo, "status", "--short"), "")


if __name__ == "__main__": unittest.main(verbosity=2)
