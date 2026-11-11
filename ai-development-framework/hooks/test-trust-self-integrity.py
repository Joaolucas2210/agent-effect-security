"""R-08 (Phase 2A): what ADR 0027's pins detect, and where they go silent. Characterisation, not a wish list.

Pins are checked only inside `hooks/adf-read-hook.py`, *after* the project is found in `enabled-projects`, and only
while `$ADF_HOME/pins.json` exists. These tests pin today's behaviour so a later change to it is deliberate:
  - removing a project's own line silences that project (no decision, no record); `adf doctor` still reports it;
  - the edit is denied as `control_plane_tampered` only for projects that are *still* enabled;
  - deleting the manifest returns the host to "not pinned" (later tampering is not detected; doctor exits 3);
  - the Codex registration (`~/.codex/hooks.json`) is not part of the snapshot.
Every run uses a throwaway HOME/ADF_HOME under TMPDIR; the real `~/.adf` and `~/.claude` are never read.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks/adf-read-hook.py"
sys.path.insert(0, str(ROOT))
from integration import control_plane_pins as pins  # noqa: E402

COMMAND = 'A=/x/adf; [ -x "$A" ] || exit 0; exec "$A" hook'


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], check=True, capture_output=True)


class TrustSelfIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.user_home = base / "home"; self.home = self.user_home / ".adf"
        (self.user_home / ".claude").mkdir(parents=True); self.home.mkdir(mode=0o700)
        self.repos = [self.make_repo(base / name) for name in ("proj-a", "proj-b")]
        (self.home / "enabled-projects").write_text("".join(f"{repo}\n" for repo in self.repos))
        (self.user_home / ".claude/settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": m, "hooks": [{"type": "command", "command": COMMAND}]} for m in ("Read", "Bash", "Grep|Glob|Edit|Write|MultiEdit|NotebookEdit", "mcp__.*")]}}))
        self.policy = base / "policy.json"; self.policy.write_text('{"schema_version":"1.0"}')
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.user_home), "ADF_HOME": str(self.home), "ADF_READ_POLICY_FILE": str(self.policy)}

    @staticmethod
    def make_repo(path):
        path.mkdir(); (path / "README.md").write_text("public"); (path / "config").mkdir(); (path / "config/.env").touch()
        git(path, "init", "-q"); git(path, "add", "-f", "."); git(path, "commit", "-qm", "f")
        return path

    def pin(self):
        with mock.patch.dict(os.environ, {**os.environ, **self.env}, clear=True):
            pins.write_manifest(self.home / "pins.json", pins.snapshot(ROOT, self.home))

    def run_hook(self, repo, tool="Edit", tool_input=None):
        """-> deny reason, or None for 'no decision' (empty stdout)."""
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "sess-trust", "tool_input": tool_input or {"file_path": str(repo / "config/.env"), "old_string": "a", "new_string": "b"}}
        proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env={**self.env, "CLAUDE_PROJECT_DIR": str(repo)}, timeout=120)
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        decision = json.loads(proc.stdout) if proc.stdout.strip() else {}  # `{}` is the Codex-shaped "no block"
        return decision["hookSpecificOutput"]["permissionDecisionReason"] if decision else None

    def doctor(self):
        proc = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(['doctor']))", str(ROOT)], capture_output=True, text=True, env={**self.env, "PYTHONPATH": str(ROOT)}, timeout=120)
        return proc.returncode, proc.stdout + proc.stderr

    def records(self):
        evidence = self.home / "evidence"
        return sorted(str(p.relative_to(evidence)) for p in evidence.rglob("*") if p.is_file()) if evidence.exists() else []

    # --- baseline: the pin works while the project stays enabled ---------------------------------------------

    def test_baseline_pinned_and_enabled_detects_policy_swap(self):
        self.pin(); self.policy.write_text('{"schema_version":"1.0","servers":{}}')
        self.assertIn("control_plane_tampered", self.run_hook(self.repos[0]))

    # --- silent paths (R-08) -----------------------------------------------------------------------------------

    def test_removing_own_line_silences_that_project_without_record(self):
        self.pin(); (self.home / "enabled-projects").write_text("")
        self.assertIsNone(self.run_hook(self.repos[0]), "the project is no longer enabled: pins are never consulted")
        self.assertIsNone(self.run_hook(self.repos[1]), "nothing enabled: no project consults the pins either")
        self.assertEqual(self.records(), [], "no journal entry: the disengagement is invisible to ADF evidence")
        code, out = self.doctor()
        self.assertEqual(code, 1, out); self.assertIn("host:enabled-projects", out, "only an out-of-band `adf doctor` sees it")

    def test_removal_is_denied_only_for_projects_still_enabled(self):
        self.pin(); (self.home / "enabled-projects").write_text(f"{self.repos[1]}\n")
        self.assertIsNone(self.run_hook(self.repos[0]), "removed project: no decision")
        self.assertIn("control_plane_tampered", self.run_hook(self.repos[1]), "still-enabled project: the divergence denies")

    def test_deleting_the_list_file_silences_every_project(self):
        self.pin(); (self.home / "enabled-projects").unlink()
        self.assertTrue(all(self.run_hook(repo) is None for repo in self.repos))
        self.assertEqual(self.records(), [])
        self.assertEqual(self.doctor()[0], 1)

    def test_deleting_the_manifest_returns_to_not_pinned(self):
        self.pin()
        (self.home / "pins.json").unlink()  # mode 0400 does not stop the owner from unlinking it in a 0700 directory
        self.policy.write_text('{"schema_version":"1.0","servers":{}}')  # tampering after the manifest is gone
        reason = self.run_hook(self.repos[0])
        self.assertNotIn("control_plane_tampered", reason or "", "no manifest = not pinned: later tampering is not detected")
        self.assertIn("uncovered_write_denied_sensitive", reason, "the ordinary gate still decides")
        code, out = self.doctor(); self.assertEqual(code, 3, out); self.assertIn("not pinned", out)

    def test_codex_registration_is_not_in_the_snapshot(self):
        codex = self.user_home / ".codex"; codex.mkdir()
        (codex / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "^Bash$", "hooks": [{"type": "command", "command": COMMAND}]}]}}))
        self.pin()
        manifest = json.loads((self.home / "pins.json").read_text())
        self.assertEqual(manifest["registration"], ["Bash", "Grep|Glob|Edit|Write|MultiEdit|NotebookEdit", "Read", "mcp__.*"], "Claude matchers only")
        self.assertFalse([label for label in manifest["files"] if "codex" in label.lower() and label.startswith("host:")])
        (codex / "hooks.json").unlink()  # the Codex hook registration is gone
        code, out = self.doctor(); self.assertEqual(code, 0, f"removed Codex registration is not a divergence: {out}")

    # --- what an agent tool can and cannot reach (partial mitigation, not tamper resistance) --------------------

    def test_edit_tool_on_adf_home_is_denied_but_bash_rm_is_not(self):
        self.pin()
        self.assertIn("uncovered_write_denied_agent_config", self.run_hook(self.repos[0], "Write", {"file_path": str(self.home / "enabled-projects"), "content": ""}))
        self.assertIsNone(self.run_hook(self.repos[0], "Bash", {"command": f"rm -f {self.home / 'pins.json'}"}), "a Bash write is outside the read grammar: no ADF decision")


if __name__ == "__main__":
    unittest.main(verbosity=2)
