"""e2e/demo.py (`make demo`): real decisions on a throwaway fixture, honest failures, nothing left behind.

The adf under test is this checkout's code (a wrapper over integration.cli), not whatever `adf` is on PATH.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "e2e/demo.py"


class DemoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.tmpdir, self.home = base / "tmp", base / "sentinel-home"
        self.tmpdir.mkdir(); self.home.mkdir()
        self.adf = self.script(base / "adf", f'exec "{sys.executable}" -c "import sys; sys.path.insert(0, \'{ROOT}\'); from integration.cli import main; raise SystemExit(main(sys.argv[1:]))" "$@"')

    def script(self, path, body):
        path.write_text("#!/bin/sh\n" + body + "\n"); path.chmod(0o755); return path

    def demo(self, **env):
        base_env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "TMPDIR": str(self.tmpdir), "ADF_BIN": str(self.adf), **env}
        return subprocess.run([sys.executable, str(DEMO)], capture_output=True, text=True, env=base_env, timeout=300)

    def assert_nothing_left(self):
        self.assertEqual(list(self.tmpdir.iterdir()), [], "the fixture is removed on every path")
        self.assertEqual(list(self.home.iterdir()), [], "the caller's HOME (~/.adf, ~/.claude) is never touched")

    def test_three_decisions_and_both_verifications(self):
        proc = self.demo()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = proc.stdout
        for line in ("✓ Read README.md", "allow", "delivered/read_delivered", "✓ Read .env", "deny/invalid_scope", "✓ Edit .claude/settings.json",
                     "uncovered_write_denied_agent_config", "attempt journal only", "authenticity=not_checked", "authenticity=valid", "not public verification", "demo passed"):
            self.assertIn(line, out)
        self.assertEqual(out.count("Evidence Bundle"), 2)
        self.assertNotIn("not-a-real-secret", out + proc.stderr, "file content never reaches the output")
        self.assertNotIn(str(self.tmpdir), out, "no temporary paths in normal output")
        self.assert_nothing_left()

    def test_missing_adf_is_a_prerequisite_error_with_a_fix(self):
        proc = self.demo(ADF_BIN=str(self.home.parent / "nope"))
        self.assertEqual(proc.returncode, 2); self.assertIn("make install-dev", proc.stderr)
        self.assert_nothing_left()

    def test_no_decision_is_reported_as_such_never_as_a_deny(self):
        silent = self.script(self.home.parent / "silent-adf", f'if [ "$1" = hook ]; then cat >/dev/null; exit 0; fi\nexec "{self.adf}" "$@"')
        proc = self.demo(ADF_BIN=str(silent))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("none  no decision", proc.stdout); self.assertIn("demo FAILED", proc.stdout)
        self.assertNotIn("✓ Read .env", proc.stdout)
        self.assert_nothing_left()

    def test_a_crashing_cli_fails_and_still_cleans_up(self):
        broken = self.script(self.home.parent / "broken-adf", "echo boom >&2; exit 3")
        proc = self.demo(ADF_BIN=str(broken))
        self.assertEqual(proc.returncode, 1); self.assertIn("DEMO_KEEP=1", proc.stderr)
        self.assert_nothing_left()

    def test_keep_leaves_the_fixture_for_inspection(self):
        proc = self.demo(DEMO_KEEP="1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr); self.assertIn("kept:", proc.stdout)
        kept = list(self.tmpdir.iterdir()); self.assertEqual(len(kept), 1)
        self.assertTrue((kept[0] / "my-app/.env").exists())


if __name__ == "__main__": unittest.main(verbosity=2)
