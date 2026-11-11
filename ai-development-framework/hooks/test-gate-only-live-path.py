"""R-09 (ARCH-02): in `gate_only` ADF decides on the Git snapshot but the native tool reads the live checkout.

A live symlink at the file or a parent (to outside the repo, or to a sensitive file inside it) must deny, with no
bundle claiming an allow. Regular files, and edges that deliver the snapshot bytes themselves, keep their behavior.
Synthetic data only; every path lives in a temporary directory.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from integration.local_read_adapter import LocalReadAdapter, live_path_has_symlink  # noqa: E402

HOOK = ROOT / "hooks/adf-read-hook.py"
MARKER = "R09-DUMMY-MARKER"


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class GateOnlyLivePathTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.repo = self.base / "repo"; (self.repo / "docs").mkdir(parents=True)
        self.outside = self.base / "outside"; self.outside.mkdir()
        (self.outside / "secret.txt").write_text(f"{MARKER}-outside\n"); (self.outside / "a.md").write_text(f"{MARKER}-dir\n")
        (self.repo / "README.md").write_text("public\n"); (self.repo / "docs/a.md").write_text("doc\n")
        (self.repo / ".gitignore").write_text(".env\n"); (self.repo / ".env").write_text(f"TOKEN={MARKER}-inrepo\n")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "m@example.invalid"); git(self.repo, "config", "user.name", "m"); git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "f")
        self.home = self.base / "adf-home"; self.home.mkdir(); (self.home / "enabled-projects").write_text(f"{self.repo}\n")

    def replace_with_link(self, relative, target):
        live = self.repo / relative
        shutil.rmtree(live) if live.is_dir() and not live.is_symlink() else live.unlink()
        live.symlink_to(target)

    def hook(self, payload, claude=True):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.base), "ADF_HOME": str(self.home)}
        if claude: env["CLAUDE_PROJECT_DIR"] = str(self.repo)
        proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=120)
        return proc.stdout.strip()

    def read_hook(self, relative):
        return self.hook({"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "sess-r09", "tool_input": {"file_path": str(self.repo / relative)}})

    def bundles(self): return [p for p in (self.home / "evidence").rglob("*.json") if "_attempts" not in p.parts]

    def assert_denied_without_allow_evidence(self, out):
        self.assertIn('"deny"', out); self.assertIn("unsafe_file_type", out); self.assertNotIn("bundle=", out)
        self.assertEqual(self.bundles(), [], "no bundle may claim an allow for an object ADF did not decide on")
        journals = [p for p in (self.home / "evidence").rglob("*") if "_attempts" in p.parts and p.is_file()]
        self.assertTrue(any('"unsafe_file_type"' in p.read_text() for p in journals), "the attempt journal records the deny")

    def test_regular_file_is_still_allowed(self):
        out = self.read_hook("README.md"); self.assertIn('"allow"', out); self.assertEqual(len(self.bundles()), 1)

    def test_live_file_symlink_outside_the_repo_is_denied(self):
        self.replace_with_link("README.md", self.outside / "secret.txt")
        self.assert_denied_without_allow_evidence(self.read_hook("README.md"))

    def test_live_file_symlink_to_sensitive_file_inside_the_repo_is_denied(self):
        self.replace_with_link("README.md", ".env")
        self.assert_denied_without_allow_evidence(self.read_hook("README.md"))

    def test_live_parent_directory_symlink_is_denied(self):
        self.replace_with_link("docs", self.outside)
        self.assert_denied_without_allow_evidence(self.read_hook("docs/a.md"))

    def test_codex_cat_is_gated_the_same_way(self):
        self.replace_with_link("README.md", self.outside / "secret.txt")
        out = self.hook({"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "sess-r09", "cwd": str(self.repo), "tool_input": {"command": "cat README.md", "workdir": str(self.repo)}}, claude=False)
        self.assert_denied_without_allow_evidence(out)

    def test_snapshot_delivering_edges_are_unchanged(self):
        self.replace_with_link("README.md", self.outside / "secret.txt")
        adapter = LocalReadAdapter(self.repo, "HEAD", self.base / "evidence", self.base)
        for mode in (None, "mediated"):
            result = adapter.read("run-r09", "README.md", 4096, delivery_mode=mode)
            self.assertEqual((result["outcome"], result.get("content")), ("delivered", "public\n"), mode)
        self.assertEqual(adapter.read("run-r09", "README.md", 4096, delivery_mode="gate_only")["outcome"], "deny")

    def test_lstat_walk_never_follows_and_leaves_missing_paths_to_the_snapshot(self):
        self.assertFalse(live_path_has_symlink(self.repo, "README.md"))
        self.assertFalse(live_path_has_symlink(self.repo, "missing/file.md"))
        self.assertFalse(live_path_has_symlink(self.repo, "README.md/child"))
        self.replace_with_link("docs", self.outside)
        self.assertTrue(live_path_has_symlink(self.repo, "docs/a.md"))


if __name__ == "__main__": unittest.main(verbosity=2)
