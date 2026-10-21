"""REQ-MP-02: the project-list CLI only writes canonical paths the hook will honor, and never shows evidence bodies."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "hooks/adf-projects.py"
_SPEC = importlib.util.spec_from_file_location("adf_read_hook", ROOT / "hooks/adf-read-hook.py")
hook = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(hook)


class AdfProjectsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.home, self.repo, self.plain = base / "adf-home", base / "proj", base / "plain"
        (self.repo / "sub").mkdir(parents=True); self.plain.mkdir()
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        self.link = base / "link"; self.link.symlink_to(self.repo)

    def run_cli(self, *args):
        result = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, env={"PATH": os.environ["PATH"], "ADF_HOME": str(self.home)}, timeout=60)
        return result.returncode, result.stdout, result.stderr

    def listed(self): return (self.home / "enabled-projects").read_text().splitlines() if (self.home / "enabled-projects").exists() else None

    def enabled_by_hook(self):
        os.environ["ADF_HOME"] = str(self.home)
        try: return hook.enabled_projects()
        finally: del os.environ["ADF_HOME"]

    def test_enable_rejects_everything_the_hook_would_ignore(self):
        for bad in ("proj", f"{self.repo}/", f"{self.repo.parent}/x/../{self.repo.name}", f"{self.repo.parent}//{self.repo.name}", str(self.repo / "missing"), str(self.repo / "sub/../sub/.")):
            with self.subTest(path=bad):
                code, out, err = self.run_cli("enable", bad)
                self.assertEqual(code, 1); self.assertIn("rejected", err); self.assertEqual(out, "")
        self.assertIsNone(self.listed(), "a rejected path never creates the list")
        self.assertEqual(self.run_cli("enable")[0], 2); self.assertEqual(self.run_cli("bogus")[0], 2)
        code, _, err = self.run_cli("enable", "")  # `make project-enable` without PROJECT
        self.assertEqual(code, 1); self.assertIn("PROJECT=/abs/git/root", err); self.assertIsNone(self.listed())
        self.assertEqual(self.run_cli("disable", "")[0], 1, "an empty disable must not resolve to the cwd")

    def test_enable_list_disable_round_trip_through_the_hook_rules(self):
        self.assertEqual(self.run_cli("enable", str(self.repo))[0], 0)
        self.assertEqual(self.run_cli("enable", str(self.repo))[1].strip(), f"already enabled: {self.repo}")
        self.assertEqual(self.run_cli("enable", str(self.link))[1].strip(), f"already enabled: {self.repo}", "symlinks resolve to the real path")
        code, _, err = self.run_cli("enable", str(self.plain))
        self.assertEqual(code, 0); self.assertIn("project_not_git", err)
        self.assertEqual(self.listed(), [str(self.repo), str(self.plain)])
        self.assertEqual(oct((self.home / "enabled-projects").stat().st_mode & 0o777), "0o600")
        self.assertEqual(self.enabled_by_hook(), frozenset({str(self.repo), str(self.plain)}))
        out = self.run_cli("list")[1]
        self.assertIn(f"enabled  {self.repo}  [git-root]", out); self.assertIn("project_not_git", out)
        self.assertEqual(self.run_cli("disable", str(self.link))[1].strip(), f"disabled: {self.repo}")
        self.assertEqual(self.run_cli("disable", str(self.repo))[1].strip(), f"not enabled: {self.repo}")
        self.assertEqual(self.listed(), [str(self.plain)])

    def test_hand_written_non_canonical_lines_are_kept_but_listed_as_ignored(self):
        self.home.mkdir(); (self.home / "enabled-projects").write_text(f"{self.repo}/\n")
        self.run_cli("enable", str(self.plain))
        self.assertEqual(self.listed(), [f"{self.repo}/", str(self.plain)])
        self.assertIn(f"ignored  {self.repo}/  [not canonical]", self.run_cli("list")[1])
        self.assertEqual(self.enabled_by_hook(), frozenset({str(self.plain)}))

    def test_reasons_counts_without_file_bodies(self):
        day = self.home / "evidence" / "proj-abcd1234" / "2026-10-20"
        (day / "s1").mkdir(parents=True); (day / "_attempts").mkdir(); (day / "_a2a").mkdir()
        (day / "s1" / "a.json").write_text(json.dumps({"reason_code": "admit_read", "receipt": {"reason_code": "read_delivered"}, "bundle_id": "SECRET-BODY"}))  # admitted: the receipt says what happened
        for name in ("b", "c"): (day / "s1" / f"{name}.json").write_text(json.dumps({"reason_code": "invalid_scope", "receipt": None}))
        (day / "_a2a" / "r.json").write_text(json.dumps({"reason_code": "input_required"}))
        (day / "_attempts" / "x.jsonl").write_text('{"reason_code":"never_counted"}\n'); (day / "s1" / "broken.json").write_text("{")
        self.assertEqual(self.run_cli("reasons")[1].splitlines()[0], "proj-abcd1234  total=5  input_required=1 invalid_scope=2 read_delivered=1 unreadable=1")
        self.assertNotIn("SECRET-BODY", self.run_cli("reasons")[1])
        (self.home / "evidence").rename(self.home / "gone")
        self.assertEqual(self.run_cli("reasons")[1].strip(), "no evidence yet")


    def test_reasons_counts_journal_attempts_and_principals_without_paths(self):
        day = self.home / "evidence" / "proj-abcd1234" / "2026-10-21"
        (day / "sess").mkdir(parents=True); (day / "_attempts").mkdir(); (day / "_a2a").mkdir()
        bundle = "b" * 64
        (day / "sess" / f"{bundle}.json").write_text(json.dumps({"bundle_id": bundle, "reason_code": "admit_read", "receipt": {"reason_code": "read_delivered"}, "effective_scope": {"kind": "filesystem", "path": "src/backend/app.py"}}))
        def journal(name, sub, reason, outcome, bundle_id):
            lines = [{"phase": "started", "payload": {"principal_sub": sub} if sub else {}}, {"phase": "completed", "payload": {"outcome": outcome, "reason_code": reason, "bundle_id": bundle_id}}]
            (day / "_attempts" / f"{name}.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))
        journal("a1", "claude:backend-reviewer", "read_delivered", "delivered", bundle)
        journal("a2", "claude:backend-reviewer", "read_delivered", "delivered", bundle)  # same path twice: one distinct path read
        journal("a3", "claude:security-reviewer", "invalid_referenced_contract", "deny", None)  # root .env: journal only, no bundle
        journal("a4", None, "invalid_scope", "deny", None)
        (day / "_attempts" / "a5.jsonl").write_text(json.dumps({"phase": "started", "payload": {}}) + "\n")  # interrupted
        (day / "_a2a" / "r1.json").write_text(json.dumps({"reason_code": "read_delivered", "outcome": "delivered", "bundle_id": bundle, "principal": {"sub": "agent-alpha", "scopes": ["workspace:read"]}}))
        (day / "_a2a" / "r2.json").write_text(json.dumps({"reason_code": "principal_not_allowlisted", "outcome": "deny", "bundle_id": None, "principal": {"sub": "agent-nobody"}}))
        out = self.run_cli("reasons")[1].splitlines()
        self.assertIn("proj-abcd1234  total=3  principal_not_allowlisted=1 read_delivered=2", out)
        self.assertIn("proj-abcd1234  attempts=5  incomplete=1 invalid_referenced_contract=1 invalid_scope=1 read_delivered=2", out)
        self.assertIn("proj-abcd1234  principal=claude:backend-reviewer  attempts=2 delivered=2 denied=0 paths_read=1", out)
        self.assertIn("proj-abcd1234  principal=claude:security-reviewer  attempts=1 delivered=0 denied=1 paths_read=0", out)
        self.assertIn("proj-abcd1234  principal=agent-alpha  attempts=1 delivered=1 denied=0 paths_read=1", out)
        self.assertNotIn("src/backend", "\n".join(out), "paths never appear, only counts")
        policy = Path(self.temp.name) / "policy.json"
        policy.write_text(json.dumps({"policy": {"rules": [{"allowed_scopes": [1, 2, 3]}], "principal_rules": [{"sub": "claude:backend-reviewer", "allowed_scopes": [1, 2, 3]}, {"sub": "agent-alpha", "allowed_scopes": [1]}]}}))
        out = self.run_cli("reasons", "--policy", str(policy))[1].splitlines()
        self.assertIn("proj-abcd1234  principal=claude:backend-reviewer  attempts=2 delivered=2 denied=0 paths_read=1 granted=3 unused=2", out)
        self.assertIn("proj-abcd1234  principal=agent-alpha  attempts=1 delivered=1 denied=0 paths_read=1 granted=1 unused=0", out)
        self.assertIn("proj-abcd1234  principal=claude:security-reviewer  attempts=1 delivered=0 denied=1 paths_read=0 granted=0 (not named in policy)", out)
        policy.write_text(json.dumps({"policy": {"rules": [{"allowed_scopes": [1, 2]}]}}))  # no principal_rules: host allowlist for everyone
        self.assertIn("proj-abcd1234  principal=agent-nobody  attempts=1 delivered=0 denied=1 paths_read=0 granted=2 unused=2", self.run_cli("reasons", "--policy", str(policy))[1].splitlines())
        self.assertEqual(self.run_cli("reasons", "--policy")[0], 2)


if __name__ == "__main__": unittest.main(verbosity=2)
