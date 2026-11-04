"""ADR 0027: a host-pinned manifest detects tampering with ADF's own code, host files and hook registration.

Negative first: edited project list, swapped policy bytes, modified gate script, removed matcher, manifest
with wrong mode -> `control_plane_tampered` and deny; no manifest -> unchanged behaviour.
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
from integration import control_plane_pins as pins  # noqa: E402


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class ControlPlanePinsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.user_home, self.repo = base / "home", base / "proj"
        self.home = self.user_home / ".adf"
        (self.user_home / ".claude").mkdir(parents=True); self.home.mkdir(); self.repo.mkdir()
        (self.repo / "README.md").write_text("public"); (self.repo / "config").mkdir(); (self.repo / "config/.env").touch()
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "-f", "."); git(self.repo, "commit", "-qm", "f")
        (self.home / "enabled-projects").write_text(f"{self.repo}\n")
        self.settings = self.user_home / ".claude/settings.json"
        command = 'A=/x/adf; [ -x "$A" ] || exit 0; exec "$A" hook'
        self.settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": m, "hooks": [{"type": "command", "command": command}]} for m in ("Read", "Bash", "Grep|Glob|Edit|Write|MultiEdit|NotebookEdit", "mcp__.*")]}}))
        self.policy = base / "policy.json"; self.policy.write_text('{"schema_version":"1.0"}')
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.user_home), "ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo), "ADF_READ_POLICY_FILE": str(self.policy)}

    def run_hook(self, tool="Edit", tool_input=None):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "sess-pins", "tool_input": tool_input or {"file_path": str(self.repo / "config/.env"), "old_string": "a", "new_string": "b"}}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"] if result.stdout.strip() else None

    def doctor(self, *args):
        proc = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))", str(ROOT), "doctor", *args], capture_output=True, text=True, env={**self.env, "PYTHONPATH": str(ROOT)})
        return proc.returncode, proc.stdout + proc.stderr

    def pin(self):
        with_env = {**os.environ, **self.env}
        with unittest.mock.patch.dict(os.environ, with_env, clear=True):
            pins.write_manifest(self.home / "pins.json", pins.snapshot(ROOT, self.home))

    def test_without_manifest_nothing_changes(self):
        self.assertIn("uncovered_write_denied_sensitive", self.run_hook())
        self.assertEqual(self.doctor()[0], 3, "not pinned is its own exit code, never green")

    def test_manifest_is_owner_read_only_and_covers_code_host_files_and_registration(self):
        self.pin()
        manifest = self.home / "pins.json"
        self.assertEqual(oct(manifest.stat().st_mode & 0o777), oct(0o400))
        data = json.loads(manifest.read_text())
        for label in ("hooks/adf-read-hook.py", "hooks/adf-deny-gate.py", "hooks/claude-code-read-gate.py", "hooks/codex-bash-read-gate.py", "integration/control_plane_pins.py", "tools/pdp.py", "runtime/pep.py", "runtime/v1/policies/sensitive-path-policy-v1.json", "host:enabled-projects", "host:ADF_READ_POLICY_FILE"):
            self.assertIn(label, data["files"], label)
        self.assertEqual(data["registration"], ["Bash", "Grep|Glob|Edit|Write|MultiEdit|NotebookEdit", "Read", "mcp__.*"])
        self.assertEqual(self.doctor()[0], 0)
        self.assertIn("uncovered_write_denied_sensitive", self.run_hook(), "untouched install: the gate decides as before")

    def test_each_tamper_is_detected_and_denies(self):
        self.pin()
        cases = (
            ("enabled-projects edited", lambda: (self.home / "enabled-projects").write_text(f"{self.repo}\n/tmp/other\n")),
            ("policy bytes swapped", lambda: self.policy.write_text('{"schema_version":"1.0","servers":{}}')),
            ("hook matcher removed", lambda: self.settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": 'exec "/x/adf" hook'}]}]}}))),
            ("registration deleted", lambda: self.settings.write_text("{}")),
            ("manifest readable by others", lambda: (self.home / "pins.json").chmod(0o644)),
            ("manifest not json", lambda: ((self.home / "pins.json").chmod(0o600), (self.home / "pins.json").write_text("{nope"), (self.home / "pins.json").chmod(0o400))),
        )
        for name, tamper in cases:
            with self.subTest(name):
                self.setUp(); self.pin(); tamper()
                self.assertIn("control_plane_tampered", self.run_hook(), name)
                code, out = self.doctor(); self.assertEqual(code, 1, out)

    def test_gate_script_modification_is_detected(self):
        self.pin()
        manifest = json.loads((self.home / "pins.json").read_text())
        manifest["files"]["hooks/adf-deny-gate.py"] = "0" * 64  # equivalent to the script having changed since the pin
        (self.home / "pins.json").chmod(0o600); (self.home / "pins.json").write_text(json.dumps(manifest)); (self.home / "pins.json").chmod(0o400)
        self.assertIn("control_plane_tampered", self.run_hook())
        code, out = self.doctor(); self.assertEqual(code, 1); self.assertIn("hooks/adf-deny-gate.py", out)

    def test_tamper_denies_before_any_gate_including_read(self):
        self.pin(); (self.home / "enabled-projects").write_text(f"{self.repo}\n/tmp/x\n")
        self.assertIn("control_plane_tampered", self.run_hook("Read", {"file_path": str(self.repo / "README.md")}))
        self.assertFalse((self.home / "evidence").exists(), "no adapter ran: nothing persisted")

    def test_doctor_pin_writes_and_repins(self):
        code, out = self.doctor("--pin"); self.assertEqual(code, 0, out); self.assertTrue((self.home / "pins.json").exists())
        (self.home / "enabled-projects").write_text(f"{self.repo}\n/tmp/x\n")
        self.assertEqual(self.doctor()[0], 1)
        self.assertEqual(self.doctor("--pin")[0], 0, "a human re-pins after a legitimate change")
        self.assertEqual(self.doctor()[0], 0)
        self.assertNotEqual(self.doctor("--bogus")[0], 0)


if __name__ == "__main__":
    import unittest.mock  # noqa: F401
    unittest.main(verbosity=2)
