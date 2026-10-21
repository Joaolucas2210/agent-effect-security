"""Optional deployment is not optional package integrity."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("host_deployment", ROOT / "hooks/check-host-deployment.py")
deployment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployment)


class HostDeploymentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.host = Path(self.temp.name)
        self.core = self.host / "ai-development-framework"
        for name in ("quality-gates.yml", "maintenance-routines.yml"):
            target = self.core / ".github/workflows" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("canonical fixture\n")

    def check(self):
        with redirect_stdout(io.StringIO()) as output:
            status = deployment.check_host_deployment(self.core)
        return status, output.getvalue()

    def configured(self):
        config = {"hooks": {"PreToolUse": [{"matcher": "^Bash$", "hooks": [{"command": "bash ai-development-framework/hooks/codex-bash-read-gate.wrapper.sh", "timeout": 30}]}]}}
        path = self.host / ".codex/hooks.json"
        path.parent.mkdir()
        path.write_text(json.dumps(config))
        path = self.host / ".github/workflows"
        path.mkdir(parents=True)
        for name in ("quality-gates.yml", "maintenance-routines.yml"):
            (path / name).write_text("canonical fixture\n")

    def test_missing_clone_deployments_fail(self):
        self.assertEqual(self.check()[0], 1)

    def test_missing_portable_deployments_are_explicit_skips(self):
        (self.host / "Makefile.adf").write_text("# portable installation\n")
        status, output = self.check()
        self.assertEqual(status, 77)
        self.assertEqual(output.count("skipped:"), 3)
        self.assertNotIn("✓", output)
        self.assertNotIn(str(self.host), output)

    def test_present_invalid_configuration_fails_even_with_skips(self):
        (self.host / "Makefile.adf").write_text("# portable installation\n")
        path = self.host / ".codex/hooks.json"
        path.parent.mkdir()
        path.write_text('{"private": "must-not-appear"}')
        status, output = self.check()
        self.assertEqual(status, 1)
        self.assertNotIn("must-not-appear", output)

    def test_valid_deployments_pass_and_drift_is_rejected(self):
        (self.host / "Makefile.adf").write_text("# portable installation\n")
        self.configured()
        self.assertEqual(self.check()[0], 0)
        (self.host / ".github/workflows/quality-gates.yml").write_text("drift\n")
        self.assertEqual(self.check()[0], 1)

    def test_missing_package_template_is_failure(self):
        (self.host / "Makefile.adf").write_text("# portable installation\n")
        (self.core / ".github/workflows/quality-gates.yml").unlink()
        self.assertEqual(self.check()[0], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
