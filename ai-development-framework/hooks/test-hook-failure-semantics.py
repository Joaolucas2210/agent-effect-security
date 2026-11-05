"""Failure semantics of the supplied hook path, characterised end to end (README "Trust model", BOUNDARY).

What happens when ADF cannot decide. Each case asserts the client-visible answer (deny JSON, or *no output*,
which every supported client treats as "ADF made no decision": the client's own permissions apply) and whether
ADF left any record. "No record" is never evidence of a block.
"""
import importlib.util
import io
import json
import contextlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
_HOOK = importlib.util.spec_from_file_location("adf_read_hook", ROOT / "hooks/adf-read-hook.py")
hook = importlib.util.module_from_spec(_HOOK); _HOOK.loader.exec_module(hook)
_CLI = importlib.util.spec_from_file_location("adf_cli", ROOT / "integration/cli.py")
cli = importlib.util.module_from_spec(_CLI); _CLI.loader.exec_module(cli)


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


class HookFailureSemanticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve(); self.repo, self.home = base / "repo", base / "adf-home"
        self.repo.mkdir(); self.home.mkdir(); (self.repo / "README.md").write_text("public")
        git(self.repo, "init", "-q"); git(self.repo, "add", "."); git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "f")
        self.env = patch.dict(os.environ, {"ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo)}); self.env.start(); self.addCleanup(self.env.stop)
        self.payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "s", "tool_input": {"file_path": str(self.repo / "README.md")}})

    def enable(self): (self.home / "enabled-projects").write_text(f"{self.repo}\n")

    def records(self): return sorted(p.name for p in (self.home / "evidence").rglob("*") if p.is_file()) if (self.home / "evidence").exists() else []

    def main_output(self, stdin):
        out = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
            self.assertEqual(hook.main(), 0)
        return out.getvalue().strip()

    def deny_reason(self, output):
        return json.loads(output)["hookSpecificOutput"]["permissionDecisionReason"]

    # --- no decision: the client proceeds under its own permissions -------------------------------------------

    def test_missing_executable_in_the_supplied_wrapper_is_no_decision(self):
        snippet = io.StringIO()
        with contextlib.redirect_stdout(snippet), contextlib.redirect_stderr(io.StringIO()):
            cli.cmd_hook_snippet(["claude"])
        command = json.loads(snippet.getvalue())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        command = command.replace(str(Path(sys.executable).parent / "adf"), str(Path(self.temp.name) / "missing-adf"))
        self.enable()  # even for an enabled project
        proc = subprocess.run(["sh", "-c", command], input=self.payload, capture_output=True, text=True, timeout=30)
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))
        self.assertEqual(self.records(), [], "no ADF record: the attempt is invisible to ADF")

    def test_hook_script_that_cannot_load_is_no_decision(self):
        self.enable()
        out = io.StringIO()
        with patch.object(cli, "_script", side_effect=ImportError("broken install")), patch.object(sys, "stdin", io.StringIO(self.payload)), contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_hook([]), 0)
        self.assertEqual(out.getvalue(), ""); self.assertEqual(self.records(), [])

    def test_failure_before_the_project_is_known_to_be_enabled_is_no_decision(self):
        self.enable()
        with patch.object(hook, "enabled_projects", side_effect=OSError("unreadable list")):
            self.assertEqual(self.main_output(self.payload), "")
        self.assertEqual(self.records(), [])

    def test_project_not_enabled_is_no_decision(self):
        self.assertEqual(self.main_output(self.payload), "")

    def test_malformed_payload_without_a_host_project_dir_is_no_decision(self):
        self.enable()
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": ""}):  # Codex shape: the project comes only from the payload's cwd
            self.assertEqual(self.main_output("{not json"), "")

    # --- deny: inside an enabled project, failure closes ----------------------------------------------------

    def test_adapter_exception_in_an_enabled_project_is_a_deny(self):
        self.enable()
        with patch.object(hook, "_gate", side_effect=RuntimeError("adapter blew up")):
            self.assertIn("adapter_failed", self.deny_reason(self.main_output(self.payload)))

    def test_malformed_payload_with_a_host_project_dir_is_a_deny(self):
        self.enable()
        self.assertIn("unsupported_tool", self.deny_reason(self.main_output("{not json")))

    def test_unsupported_tool_in_an_enabled_project_is_a_deny(self):
        self.enable()
        self.assertIn("unsupported_tool", self.deny_reason(self.main_output(json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Teleport", "session_id": "s", "tool_input": {}}))))


if __name__ == "__main__": unittest.main(verbosity=2)
