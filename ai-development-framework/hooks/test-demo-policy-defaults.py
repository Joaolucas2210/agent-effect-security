"""Phase 2A (R-10/ARCH-03): the reference demo policy is never mistaken for a reviewed allowlist.

`adf doctor`, `adf hook-snippet` and `adf projects enable` name the read policy in effect (pinned / reference demo /
host_policy_invalid) as a diagnostic only: exit codes, the snippet JSON and the enable stdout are unchanged, and the
doctor's verdict for each configuration matches what the adapter actually does with it.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from integration.local_read_adapter import LocalReadAdapter  # noqa: E402

CLI = "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))"
HOOK_CMD = 'A=/x/adf; [ -x "$A" ] || exit 0; exec "$A" hook'


def git(cwd, *args): return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class DemoPolicyDefaultsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.user_home, self.repo = self.base / "home", self.base / "proj"; self.home = self.user_home / ".adf"
        (self.user_home / ".claude").mkdir(parents=True); self.home.mkdir(); self.repo.mkdir(); (self.repo / "README.md").write_text("public")
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "d@example.invalid"); git(self.repo, "config", "user.name", "d"); git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "f")
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.user_home), "ADF_HOME": str(self.home), "PYTHONPATH": str(ROOT)}
        self.policy = self.base / "policy.json"
        code, out, err = self.adf("policy", "build", "--run-id", "run-host", "--allow", "README.md", "--out", str(self.policy))
        self.assertEqual(code, 0, err)
        self.pin = out.split("ADF_READ_POLICY_SHA256=", 1)[1].split()[0]

    def adf(self, *argv, **env):
        proc = subprocess.run([sys.executable, "-c", CLI, str(ROOT), *argv], capture_output=True, text=True, env={**self.env, **env}, timeout=120)
        return proc.returncode, proc.stdout, proc.stderr

    def register(self, prefix=""):
        hook = {"type": "command", "command": prefix + HOOK_CMD}
        (self.user_home / ".claude/settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": [hook]}]}}))

    def test_default_is_the_reference_demo_and_says_so_without_changing_exit_codes(self):
        code, out, _ = self.adf("doctor")
        self.assertEqual(code, 3, "not pinned stays exit 3; the policy line is a diagnostic only")
        self.assertIn("read policy: reference demo", out); self.assertIn("not a reviewed allowlist", out)
        self.assertEqual(self.adf("doctor", "--pin")[0], 0)
        code, out, _ = self.adf("doctor")
        self.assertEqual(code, 0, "an intact control plane on the demo policy keeps exit 0 (proposal, not implemented: fail it)")
        self.assertIn("reference demo", out); self.assertIn("control plane intact", out)
        result = LocalReadAdapter(self.repo, "HEAD", self.base / "evidence").read("run-host", "README.md", 64)
        self.assertEqual(result["outcome"], "delivered", "the demo grants the requested non-sensitive path: what the warning says")

    def test_pinned_policy_from_the_shell_or_the_registration_overrides_the_demo(self):
        code, out, _ = self.adf("doctor", ADF_READ_POLICY_FILE=str(self.policy), ADF_READ_POLICY_SHA256=self.pin)
        self.assertEqual(code, 3); self.assertIn("read policy: pinned host policy, pin verified", out); self.assertNotIn("reference demo", out)
        self.assertNotIn(str(self.policy), out, "labels, never host paths")
        self.register(f"export ADF_READ_POLICY_FILE={self.policy} ADF_READ_POLICY_SHA256={self.pin}; ")
        code, out, _ = self.adf("doctor")
        self.assertIn("pin verified", out, "a terminal without the variables sees what the registered hook command exports")
        code, out, _ = self.adf("doctor", ADF_READ_POLICY_SHA256="0" * 64)
        self.assertIn("host_policy_invalid", out, "the shell value wins over the registration")
        adapter = LocalReadAdapter(self.repo, "HEAD", self.base / "evidence", host_policy_path=str(self.policy), host_policy_sha256=self.pin)
        self.assertEqual(adapter.read("run-host", "README.md", 64)["outcome"], "delivered")

    def test_invalid_configurations_are_reported_as_host_policy_invalid_like_the_adapter_denies_them(self):
        bad = self.base / "bad.json"; bad.write_text("{not json")
        other = self.base / "other.json"; other.write_text(json.dumps({"schema_version": "1.0"}))
        cases = {
            "partial": {"ADF_READ_POLICY_FILE": str(self.policy)},
            "partial ": {"ADF_READ_POLICY_SHA256": self.pin},
            "not absolute": {"ADF_READ_POLICY_FILE": "policy.json", "ADF_READ_POLICY_SHA256": self.pin},
            "file missing": {"ADF_READ_POLICY_FILE": str(self.base / "missing.json"), "ADF_READ_POLICY_SHA256": self.pin},
            "not JSON": {"ADF_READ_POLICY_FILE": str(bad), "ADF_READ_POLICY_SHA256": self.pin},
            "pin mismatch": {"ADF_READ_POLICY_FILE": str(self.policy), "ADF_READ_POLICY_SHA256": "0" * 64},
            "not a host policy": {"ADF_READ_POLICY_FILE": str(other), "ADF_READ_POLICY_SHA256": self.pin},
            "empty": {"ADF_READ_POLICY_FILE": "", "ADF_READ_POLICY_SHA256": ""},
        }
        for label, env in cases.items():
            with self.subTest(label):
                code, out, _ = self.adf("doctor", **env)
                self.assertEqual(code, 3, "exit code unchanged by the policy diagnostic")
                self.assertIn("✗ read policy: host_policy_invalid", out); self.assertIn("every read in an enabled project is denied", out)
                self.assertNotIn("reference demo", out, "an invalid configuration never falls back to the demo")
                for value in env.values():
                    if len(value) > 1 and value != self.pin and value != "0" * 64: self.assertNotIn(value, out, "path-free")
                kwargs = {"host_policy_path": env.get("ADF_READ_POLICY_FILE"), "host_policy_sha256": env.get("ADF_READ_POLICY_SHA256")}
                result = LocalReadAdapter(self.repo, "HEAD", self.base / "evidence", **kwargs).read("run-host", "README.md", 64)
                self.assertEqual((result["outcome"], result["reason_code"]), ("deny", "host_policy_invalid"), "the doctor names what the adapter does")

    def test_hook_snippet_warns_on_stderr_and_keeps_the_json(self):
        code, demo_out, demo_err = self.adf("hook-snippet", "claude")
        self.assertEqual(code, 0); self.assertIn("reference demo policy", demo_err); self.assertIn("not a reviewed allowlist", demo_err)
        code, pinned_out, pinned_err = self.adf("hook-snippet", "claude", ADF_READ_POLICY_FILE=str(self.policy), ADF_READ_POLICY_SHA256=self.pin)
        self.assertEqual(code, 0); self.assertNotIn("reference demo", pinned_err)
        self.assertEqual(demo_out, pinned_out, "stdout JSON is identical: the policy is never written into the registration")
        self.assertNotIn("ADF_READ_POLICY", demo_out)

    def test_projects_enable_warns_on_stderr_and_keeps_stdout(self):
        code, out, err = self.adf("projects", "enable", str(self.repo))
        self.assertEqual((code, out), (0, f"enabled: {self.repo}\n")); self.assertIn("reference demo policy", err)
        self.adf("projects", "disable", str(self.repo))
        code, out, err = self.adf("projects", "enable", str(self.repo), ADF_READ_POLICY_FILE=str(self.policy), ADF_READ_POLICY_SHA256=self.pin)
        self.assertEqual((code, out, err), (0, f"enabled: {self.repo}\n", ""))


if __name__ == "__main__": unittest.main(verbosity=2)
