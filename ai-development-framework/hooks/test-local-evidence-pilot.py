"""Independent checks for the isolated H4 local-evidence pilot."""
import hashlib
import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
from integration.evidence_trial_metrics import verify_trial_report

_SPEC = importlib.util.spec_from_file_location("local_evidence_pilot", ROOT / "hooks/run-local-evidence-pilot.py")
pilot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pilot)


def load(path): return json.loads(path.read_text())
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def tree_digest(root): return {str(path.relative_to(root)): digest(path) for path in root.rglob("*") if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts}
def snapshot(path): return digest(path) if path.is_file() else tree_digest(path)


class LocalEvidencePilotTest(unittest.TestCase):
    def schemas(self):
        return {"evidence_bundle": load(ROOT / "integration/v1/schemas/evidence-bundle.schema.json"), "runtime_audit_receipt": load(ROOT / "runtime/v1/schemas/runtime-audit-receipt.schema.json"), "evidence_trial_observation": load(ROOT / "integration/v1/schemas/evidence-trial-observation.schema.json"), "evidence_trial_report": load(ROOT / "integration/v1/schemas/evidence-trial-report.schema.json")}

    def test_trusted_surface_bindings_and_redacted_report(self):
        source = (ROOT / "hooks/run-local-evidence-pilot.py").read_text().lower()
        for forbidden in ("import subprocess", "from subprocess", "subprocess.", "import os", "os.system", "git", "shell", "socket", "requests", "docker", "mcp", "urllib", "http.client", "getenv", "environ", "sys.argv"):
            self.assertNotIn(forbidden, source)
        self.assertEqual(pilot.TRUSTED_REPOSITORY, ROOT.parent)
        observations, identities = pilot._trials(pilot._schemas())
        self.assertEqual(len(observations), 3)
        self.assertEqual(len({item["workspace_id"] for item in identities}), 3)
        self.assertEqual(len({item["snapshot_digest"] for item in identities}), 3)
        self.assertTrue(all(item["task_ref"] == item["snapshot_digest"] == item["intent_task_ref"] for item in identities))
        report = pilot.run_pilot()
        self.assertTrue(verify_trial_report(report, self.schemas()))
        self.assertEqual((report["trial_count"], report["admit_read_total"], report["deny_total"], report["sensitive_path_denied_total"]), (3, 2, 1, 1))
        self.assertNotIn("README.md", json.dumps(report))

    def test_deny_never_calls_pep_and_sensitive_never_delivers_content(self):
        calls, original = [], pilot.PolicyEnforcementPoint
        class CountingPEP:
            def __init__(self, *args): self.inner = original(*args)
            def enforce_read(self, *args): calls.append(True); return self.inner.enforce_read(*args)
        schemas = pilot._schemas()
        with patch.object(pilot, "PolicyEnforcementPoint", CountingPEP):
            deny, _ = pilot._trial(schemas, *pilot.TRIALS[1])
            sensitive, _ = pilot._trial(schemas, *pilot.TRIALS[2])
        self.assertEqual(calls, [True])
        self.assertEqual((deny["runtime_outcome"], deny["runtime_reason_code"]), ("not_attempted", None))
        self.assertEqual((sensitive["runtime_outcome"], sensitive["runtime_reason_code"]), ("deny", "sensitive_path_denied"))
        self.assertNotIn("content", json.dumps(sensitive))

    def test_failures_are_redacted_and_do_not_return_a_report(self):
        secret = "/tmp/segredo --argv=token stderr-confidencial"
        class PrepareFails:
            def __init__(self, *_): pass
            def prepare(self, _): raise RuntimeError(secret)
        class CleanupFails:
            def __init__(self, *_): pass
            def prepare(self, _): return {"workspace_id": "ws", "snapshot_digest": "x", "task_ref": "x"}
            def cleanup(self, _): raise RuntimeError(secret)
        for manager, code in ((PrepareFails, "pilot_workspace_prepare_failed"), (CleanupFails, "pilot_workspace_cleanup_failed")):
            output = io.StringIO()
            with patch.object(pilot, "WorkspaceManager", manager), redirect_stdout(output): self.assertEqual(pilot.main(), 1)
            self.assertEqual(output.getvalue().strip(), code)
            self.assertNotIn("{", output.getvalue())
            for value in ("/tmp/segredo", "--argv=token", "stderr-confidencial", "Traceback"):
                self.assertNotIn(value, output.getvalue())

    def test_workspace_failures_are_safe_and_actionable(self):
        expected = {
            "HEAD": "workspace_worktree_prepare_failed",
            "HEAD~1": "workspace_revision_unavailable",
            "HEAD~2": "workspace_revision_unavailable",
        }
        class FailingManager:
            def __init__(self, _, revision): self.revision = revision
            def prepare(self, _): raise RuntimeError(expected[self.revision])
        for trial in pilot.TRIALS:
            output = io.StringIO()
            with patch.object(pilot, "TRIALS", (trial,)), patch.object(pilot, "WorkspaceManager", FailingManager), redirect_stdout(output): self.assertEqual(pilot.main(), 1)
            self.assertEqual(output.getvalue().strip(), expected[trial[1]])
            self.assertNotIn("{", output.getvalue())
            for value in ("/tmp/segredo", "--argv=token", "stderr-confidencial", "Traceback"):
                self.assertNotIn(value, output.getvalue())

    def test_two_runs_leave_checkout_and_evidence_unchanged(self):
        tracked = [ROOT.parent / "README.md", ROOT / "docs/evals/results.csv", ROOT / "docs/observability/events.jsonl", ROOT / "docs/traces/proposals", ROOT / "docs/traces"]
        before = {path: snapshot(path) for path in tracked if path.exists()}
        checkout_before = tree_digest(ROOT.parent)
        reports = [pilot.run_pilot(), pilot.run_pilot()]
        self.assertEqual(before, {path: snapshot(path) for path in tracked if path.exists()})
        self.assertEqual(checkout_before, tree_digest(ROOT.parent))
        fields = ("trial_count", "observations_total", "decisions_total", "admit_read_total", "deny_total", "sensitive_path_denied_total")
        self.assertEqual(tuple(reports[0][field] for field in fields), tuple(reports[1][field] for field in fields))


if __name__ == "__main__": unittest.main(verbosity=2)
