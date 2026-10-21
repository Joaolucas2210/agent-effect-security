"""REQ-MP-01: one global Read hook; gates only host-enabled projects, passes through everywhere else."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks/adf-read-hook.py"
_SPEC = importlib.util.spec_from_file_location("adf_read_hook", HOOK)
hook = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(hook)
_PACK = importlib.util.spec_from_file_location("effect_security_read_v0", ROOT / "policy-packs/effect-security-read-v0/build.py")
pack = importlib.util.module_from_spec(_PACK); _PACK.loader.exec_module(pack)
SECRET, PUBLIC, SESSION = "AKIA-mp01-fake-secret", "mp01 public readme", "sess-mp01"


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class AdfReadHookTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.home, self.repo, self.plain = base / "adf-home", base / "proj", base / "not-git"
        for path in (self.repo / "config", self.repo / "sub", self.plain): path.mkdir(parents=True)
        (self.repo / "README.md").write_text(PUBLIC); (self.repo / "config/.env").write_text(SECRET); (self.repo / "sub/notes.md").write_text("notes")
        (self.plain / "README.md").write_text(PUBLIC)
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m")
        git(self.repo, "add", "-f", "."); git(self.repo, "commit", "-qm", "fixture")

    def enable(self, *lines):
        self.home.mkdir(exist_ok=True)
        (self.home / "enabled-projects").write_text("".join(f"{line}\n" for line in lines))

    def run_hook(self, project, path, session=SESSION, **env):
        """Exactly as Claude Code runs it: a fresh process, JSON on stdin, CLAUDE_PROJECT_DIR set by the host."""
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": session, "tool_input": {"file_path": path if path.startswith("/") else str(Path(project) / path)}}
        base_env = {"PATH": os.environ["PATH"], "HOME": str(self.home.parent), "ADF_HOME": str(self.home), **({"CLAUDE_PROJECT_DIR": str(project)} if project else {}), **env}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=base_env, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def run_codex(self, cwd, command):
        """As Codex runs it: no CLAUDE_PROJECT_DIR, the session cwd in the payload and as the process cwd."""
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": SESSION, "cwd": str(cwd), "tool_input": {"command": command}}
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home.parent), "ADF_HOME": str(self.home)}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, cwd=str(cwd), timeout=120)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return json.loads(result.stdout) if result.stdout.strip() else None

    def evidence(self): return sorted((self.home / "evidence").rglob("*.json")) if (self.home / "evidence").exists() else []

    def test_pass_through_when_not_enabled(self):
        # No list, unreadable list, project absent from list, no CLAUDE_PROJECT_DIR: never decides, never writes.
        self.assertIsNone(self.run_hook(self.repo, "config/.env"))
        self.enable(str(self.plain))
        self.assertIsNone(self.run_hook(self.repo, "README.md"))
        self.assertIsNone(self.run_hook(None, str(self.repo / "README.md")))
        (self.home / "enabled-projects").unlink(); (self.home / "enabled-projects").mkdir()  # unreadable as a file
        self.assertIsNone(self.run_hook(self.repo, "config/.env"))
        self.assertEqual(self.evidence(), [])

    def test_enabled_project_is_gated_with_evidence_outside_the_repo(self):
        self.enable(str(self.repo))
        allowed, denied = self.run_hook(self.repo, "README.md"), self.run_hook(self.repo, "config/.env")
        self.assertEqual(allowed["permissionDecision"], "allow")
        self.assertEqual(denied["permissionDecision"], "deny"); self.assertIn("invalid_scope", denied["permissionDecisionReason"])
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        bundles = [path for path in self.evidence() if "_attempts" not in path.parts]
        self.assertEqual(len(bundles), 2)
        self.assertTrue(all(path.is_relative_to(self.home / "evidence" / hook.project_id(self.repo) / day) for path in bundles))
        self.assertNotIn(SECRET, "".join(path.read_text() for path in self.evidence()))
        self.assertEqual(git(self.repo, "status", "--short", "--ignored"), "", "nothing is written inside the client repo")
        self.assertEqual(git(self.repo, "worktree", "list").count("\n"), 1, "the snapshot worktree is cleaned up")

    def test_codex_cat_uses_the_same_list_root_and_evidence_dir(self):
        self.assertIsNone(self.run_codex(self.repo, "cat config/.env"), "not enabled: no decision, Codex's own policy applies")
        self.enable(str(self.repo))
        self.assertEqual(self.run_codex(self.repo, "cat README.md"), {}, "delivered = no-block (P4 contract)")
        self.assertEqual(self.run_codex(self.repo / "sub", "cat notes.md"), {}, "relative to the session cwd, root from git")
        denied = self.run_codex(self.repo, "cat config/.env")["hookSpecificOutput"]
        self.assertEqual(denied["permissionDecision"], "deny"); self.assertIn("invalid_scope", denied["permissionDecisionReason"])
        self.assertEqual(self.run_codex(self.repo, "pnpm test"), {}, "non-read commands are not ADF's call")
        self.assertIn("unsafe_read_command", self.run_codex(self.repo, "cat README.md | wc")["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIn("path_outside_trusted_root", self.run_codex(self.repo, "cat /etc/hostname")["hookSpecificOutput"]["permissionDecisionReason"])
        self.run_hook(self.repo, "README.md")  # Claude in the same project lands in the same evidence dir
        bundles = [path for path in self.evidence() if "_attempts" not in path.parts]
        self.assertEqual(len(bundles), 4)
        self.assertTrue(all(path.is_relative_to(self.home / "evidence" / hook.project_id(self.repo)) for path in bundles))
        self.assertEqual(git(self.repo, "status", "--short", "--ignored"), "")

    def test_enabled_project_fails_closed_on_unknown_tool_or_malformed_payload(self):
        self.enable(str(self.repo))
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home.parent), "ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo)}
        for stdin in (json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(self.repo), "tool_input": {}}), "{not json"):
            result = subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIsNone(self.run_codex(self.plain, "cat README.md"), "the malformed/unknown rules never reach a project that is not enabled")

    def test_subdirectory_launch_and_host_root_override(self):
        self.enable(str(self.repo))
        decision = self.run_hook(self.repo / "sub", str(self.repo / "README.md"), ADF_TRUSTED_REPOSITORY=str(self.plain))
        self.assertEqual(decision["permissionDecision"], "allow", "root comes from the enabled project, not a stale export")

    def test_non_canonical_entries_never_enable(self):
        for entry in (f"{self.repo}/", f"{self.repo.parent}/x/../{self.repo.name}", f"{self.repo.parent}//{self.repo.name}", self.repo.name, f"  # {self.repo}"):
            with self.subTest(entry=entry):
                self.enable(entry)
                self.assertIsNone(self.run_hook(self.repo, "config/.env"))

    def test_enabled_project_without_git_fails_closed(self):
        self.enable(str(self.plain))
        decision = self.run_hook(self.plain, "README.md")
        self.assertEqual(decision["permissionDecision"], "deny"); self.assertIn("project_not_git", decision["permissionDecisionReason"])

    def test_pinned_policy_pack_still_applies(self):
        target, pin = pack.write(pack.build(SESSION, ["README.md"], 1 << 20), Path(self.temp.name) / "policy.json")  # = hook default budget
        self.enable(str(self.repo))
        env = {"ADF_READ_POLICY_FILE": str(target), "ADF_READ_POLICY_SHA256": pin}
        self.assertEqual(self.run_hook(self.repo, "README.md", **env)["permissionDecision"], "allow")
        denied = self.run_hook(self.repo, "sub/notes.md", **env)
        self.assertEqual(denied["permissionDecision"], "deny"); self.assertIn("scope_not_allowlisted", denied["permissionDecisionReason"])

    def test_internal_failure_on_an_enabled_project_denies_and_otel_off_starts_no_thread(self):
        self.enable(str(self.repo))
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": SESSION, "tool_input": {"file_path": str(self.repo / "README.md")}})
        env = {"ADF_HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.repo), "PATH": os.environ["PATH"]}
        with patch.dict(os.environ, env, clear=True), patch.object(hook, "_gate", side_effect=RuntimeError("boom")):
            self.assertEqual(hook.decide(payload)["hookSpecificOutput"]["permissionDecision"], "deny")
        import integration.otel_export as otel
        with patch.dict(os.environ, env, clear=True), patch.object(otel.threading, "Thread", side_effect=AssertionError("OTel off: no thread")):
            self.assertEqual(hook.decide(payload)["hookSpecificOutput"]["permissionDecision"], "allow")


if __name__ == "__main__": unittest.main(verbosity=2)
