"""Pilot day-0 follow-ups 1-3 (PILOT-20261104 findings 1, 6, 7, 9):
- a tamper deny names the divergent labels (never a path) while the journal keeps the stable reason code;
- `adf doctor` reads host env files from the registered hook command when the shell lacks them, and prints
  the clone's branch and commit next to the verdict;
- `adf hook-snippet` exports the evidence key when the host has one.
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
from integration import control_plane_pins as pins  # noqa: E402


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class PilotErgonomicsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.user_home, self.repo = base / "home", base / "proj"; self.home = self.user_home / ".adf"
        (self.user_home / ".claude").mkdir(parents=True); self.home.mkdir(); self.repo.mkdir(); (self.repo / "README.md").write_text("public")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")
        self.key = self.home / "evidence.key"; self.key.write_bytes(b"k" * 32); self.key.chmod(0o400)
        self.policy = base / "policy.json"; self.policy.write_text('{"schema_version":"1.0"}')
        self.command = f'export ADF_EVIDENCE_KEY_FILE={self.key} ADF_READ_POLICY_FILE={self.policy}; A=/x/adf; [ -x "$A" ] || exit 0; exec "$A" hook'
        (self.user_home / ".claude/settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": m, "hooks": [{"type": "command", "command": self.command}]} for m in ("Read", "Bash", "Grep|Glob|Edit|Write|MultiEdit|NotebookEdit|WebFetch", "mcp__.*")]}}))
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.user_home), "ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo), "ADF_EVIDENCE_KEY_FILE": str(self.key), "ADF_READ_POLICY_FILE": str(self.policy)}

    def doctor(self, *args, env=None):
        proc = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))", str(ROOT), "doctor", *args], capture_output=True, text=True, env={**(env or self.env), "PYTHONPATH": str(ROOT)})
        return proc.returncode, proc.stdout + proc.stderr

    def hook(self, tool="Edit", tool_input=None):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "sess-ergo", "tool_input": tool_input or {"file_path": str(self.repo / "README.md"), "old_string": "a", "new_string": "b"}}
        proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual((proc.returncode, proc.stderr), (0, "")); return proc.stdout

    def test_tamper_deny_names_labels_but_never_a_path_and_journal_keeps_the_code(self):
        self.assertEqual(self.doctor("--pin")[0], 0)
        (self.home / "enabled-projects").write_text(f"{self.repo}\n/tmp/x\n"); self.policy.write_text("{}")
        out = self.hook()
        reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("control_plane_tampered", reason); self.assertIn("host:enabled-projects", reason); self.assertIn("host:ADF_READ_POLICY_FILE", reason)
        self.assertNotIn(str(self.policy), reason); self.assertNotIn("/tmp/x", reason)
        journal, = (self.home / "evidence").rglob("_attempts/*.jsonl")
        self.assertIn('"reason_code": "control_plane_tampered"'.replace(": ", ":"), journal.read_text().replace(": ", ":")); self.assertNotIn("host:enabled-projects", journal.read_text(), "the journal keeps the stable code only")
        many = {f"{i}.py": "x" for i in range(12)}
        self.assertLessEqual(len(pins.describe(sorted(many))), 160, "the reason stays short: first labels + a count")

    def test_doctor_reads_host_env_from_the_registration_and_prints_the_clone(self):
        self.assertEqual(self.doctor("--pin")[0], 0)
        shell = {k: v for k, v in self.env.items() if k not in ("ADF_EVIDENCE_KEY_FILE", "ADF_READ_POLICY_FILE")}
        code, out = self.doctor(env=shell)
        self.assertEqual(code, 0, out); self.assertIn("control plane intact", out)
        self.assertIn("clone:", out); self.assertIn(git(ROOT, "rev-parse", "--abbrev-ref", "HEAD").strip(), out); self.assertIn(git(ROOT, "rev-parse", "--short", "HEAD").strip(), out)
        self.assertNotIn(str(self.key), out, "the doctor prints labels, not host paths")
        self.policy.write_text("{}")
        code, out = self.doctor(env=shell); self.assertEqual(code, 1); self.assertIn("host:ADF_READ_POLICY_FILE", out, "a file named only in the registration is still compared")
        shell_other = {**shell, "ADF_READ_POLICY_FILE": str(self.policy.with_name("other.json"))}
        self.policy.with_name("other.json").write_text('{"schema_version":"1.0","other":true}')  # different bytes from the pinned file
        code, out = self.doctor(env=shell_other); self.assertEqual(code, 1, "the shell value wins over the registration and differs from the pin")

    def test_hook_snippet_exports_the_key_when_the_host_has_one(self):
        def snippet(agent, **env):
            proc = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))", str(ROOT), "hook-snippet", agent], capture_output=True, text=True, env={"PATH": os.environ["PATH"], "HOME": str(self.user_home), "ADF_HOME": str(self.home), "PYTHONPATH": str(ROOT), **env})
            self.assertEqual(proc.returncode, 0, proc.stderr); return json.loads(proc.stdout)["hooks"]["PreToolUse"]
        for agent in ("claude", "codex"):
            for entry in snippet(agent):
                command = entry["hooks"][0]["command"]
                self.assertTrue(command.startswith(f"export ADF_EVIDENCE_KEY_FILE={self.key}; "), command)
                self.assertIn('|| exit 0; exec "$A" hook', command)
        self.key.chmod(0o600); self.key.unlink()
        for entry in snippet("claude"):
            self.assertNotIn("ADF_EVIDENCE_KEY_FILE", entry["hooks"][0]["command"], "no key on the host: nothing exported")
        for entry in snippet("claude", ADF_EVIDENCE_KEY_FILE="/elsewhere/k"):
            self.assertTrue(entry["hooks"][0]["command"].startswith("export ADF_EVIDENCE_KEY_FILE=/elsewhere/k; "), "an explicit env wins")


if __name__ == "__main__": unittest.main(verbosity=2)
