"""P2 checks: the trial runner aggregates honestly, leaks nothing, and never treats evidence as authority."""
import importlib.util
import io
import json
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
from integration.evidence_trial_metrics import verify_trial_report
from integration.local_evidence_bundle import is_authorization
from runtime.local_read_runtime import LocalReadRuntime
from runtime.pep import PolicyEnforcementPoint

_SPEC = importlib.util.spec_from_file_location("local_evidence_trial", ROOT / "hooks/run-local-evidence-trial.py")
trial = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(trial)
SECRET, PUBLIC = "conteudo-secreto-do-token", "public-readme-content"
REPORT_KEYS = {"schema_version", "trial_id", "created_at", "source", "reads_total", "bundles_total", "reason_codes", "metrics"}
VOLATILE = {"trial_id", "created_at", "metrics"}  # metrics differ only by report_id/created_at/latency/sha; compared field-wise below
STABLE_METRICS = ("trial_count", "observations_total", "evidence_bundle_valid_total", "evidence_bundle_invalid_total", "decisions_total", "admit_read_total", "deny_total", "binding_mismatch_total", "sensitive_path_denied_total", "invalid_contract_total", "human_intervention_required_total")


def git(cwd, *args): subprocess.run(["git", "-C", str(cwd), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class LocalEvidenceTrialTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "source"; self.repo.mkdir()
        git(self.repo, "init", "-q"); git(self.repo, "config", "user.email", "p2@example.invalid"); git(self.repo, "config", "user.name", "P2")
        (self.repo / "README.md").write_text(PUBLIC); (self.repo / "docs").mkdir(); (self.repo / "docs/x.md").write_text("x")
        (self.repo / "secrets").mkdir(); (self.repo / "secrets/token").write_text(SECRET)
        git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "initial")
        self.evidence, self.trials = Path(self.temp.name) / "evidence", Path(self.temp.name) / "trials"
        patches = [patch.object(trial, "TRUSTED_REPOSITORY", self.repo), patch.object(trial, "EVIDENCE_DIR", self.evidence), patch.object(trial, "TRIALS_DIR", self.trials)]
        for item in patches: item.start(); self.addCleanup(item.stop)

    def run_trial(self, trial_id, **kwargs):
        output = io.StringIO()
        with redirect_stdout(output): report, records, ok = trial.run_trial(trial_id, trials_dir=self.trials, **kwargs)
        return report, records, ok

    def assert_redacted(self, text):
        for forbidden in (SECRET, PUBLIC, str(self.repo), str(self.temp.name), "README", "secrets/token", "docs/../", "content", "file_path", "prompt", "adf-h3-01-"):
            self.assertNotIn(forbidden, text, forbidden)

    def test_fixed_suite_is_deterministic_redacted_and_persisted_owner_only(self):
        first, records, ok = self.run_trial("trial-a"); second, _, _ = self.run_trial("trial-b")
        self.assertTrue(ok); self.assertEqual(set(first), REPORT_KEYS)
        self.assertEqual(first["reason_codes"], {"delivered/read_delivered": 1, "deny/invalid_referenced_contract": 1, "deny/run_binding_mismatch": 1, "deny/sensitive_path_denied": 1, "deny/task_ref_mismatch": 1})
        self.assertEqual((first["reads_total"], first["bundles_total"]), (5, 4))
        metrics = first["metrics"]
        self.assertEqual(tuple(metrics[field] for field in STABLE_METRICS), (4, 4, 4, 0, 4, 3, 1, 2, 1, 0, 0))
        self.assertEqual(metrics["decision_latency_ms"]["count"], 4); self.assertTrue(first["source"]["latency_recorded"])
        self.assertEqual(first["source"], {"kind": "fixed_suite", "suite_version": trial.SUITE_VERSION, "adapter_id": "local-read-adapter", "adapter_version": "1.0", "package_version": trial.PACKAGE_VERSION, "latency_recorded": True})
        self.assertTrue(verify_trial_report(metrics, trial.adapter_module.schemas() | {"evidence_trial_observation": trial._load(ROOT / "integration/v1/schemas/evidence-trial-observation.schema.json"), "evidence_trial_report": trial._load(ROOT / "integration/v1/schemas/evidence-trial-report.schema.json")}))
        self.assertEqual({key: value for key, value in first.items() if key not in VOLATILE}, {key: value for key, value in second.items() if key not in VOLATILE})
        self.assertEqual([metrics[field] for field in STABLE_METRICS], [second["metrics"][field] for field in STABLE_METRICS])
        stored = self.trials / "trial-a.json"; self.assertEqual(stat.S_IMODE(stored.stat().st_mode), 0o600)
        self.assert_redacted(stored.read_text()); self.assertEqual(json.loads(stored.read_text()), first)
        self.assert_redacted(trial.summary(first, records, ok))  # the summary names suite cases, never paths or content
        self.assertEqual(len(records), 5); self.assertTrue(all("content" not in record for record in records))
        with self.assertRaises(FileExistsError): trial.persist_report(first, self.trials)

    def test_ingest_counts_persisted_evidence_without_touching_pdp_pep_or_runtime(self):
        suite, _, _ = self.run_trial("trial-suite")
        (self.evidence / "_timings").mkdir()
        (self.evidence / "_timings" / "unreadable.json").write_text("not a bundle")
        (self.evidence / "garbage.json").write_text("not json")
        tampered = json.loads(next((self.evidence / "trial-suite-happy-path").glob("*.json")).read_text()); tampered["receipt"]["reason_code"] = "forged/../path"; tampered["bundle_id"] = "tampered-bundle"
        (self.evidence / "tampered.json").write_text(json.dumps(tampered))
        with patch.object(LocalReadRuntime, "read", side_effect=AssertionError("ingest must not read")), patch.object(PolicyEnforcementPoint, "enforce_read", side_effect=AssertionError("ingest must not enforce")), patch.object(trial.adapter_module, "LocalReadAdapter", side_effect=AssertionError("ingest must not decide")):
            report, records, ok = self.run_trial("trial-ingest", evidence_dir=self.evidence)
        self.assertTrue(ok); self.assertEqual(report["source"]["kind"], "persisted_evidence"); self.assertFalse(report["source"]["latency_recorded"]); self.assertIsNone(report["source"]["suite_version"])
        self.assertEqual((report["reads_total"], report["bundles_total"]), (6, 6))
        self.assertEqual(report["reason_codes"], {"delivered/read_delivered": 1, "deny/evidence_bundle_invalid": 2, "deny/run_binding_mismatch": 1, "deny/sensitive_path_denied": 1, "deny/task_ref_mismatch": 1})
        expected = dict(zip(STABLE_METRICS, (4, 6, 4, 2, 4, 3, 1, 2, 1, 0, 0)))
        self.assertEqual({field: report["metrics"][field] for field in STABLE_METRICS}, expected)
        self.assertEqual(report["metrics"]["decision_latency_ms"], {"count": 4, "sum": 0, "min": 0, "max": 0})
        self.assert_redacted(json.dumps(report)); self.assertNotIn("forged", json.dumps(report))
        self.assertTrue(all(not is_authorization(record["bundle"]) for record in records if record["bundle"] is not None))
        with self.assertRaises(RuntimeError) as failure: trial.run_trial("trial-missing", evidence_dir=self.evidence / "nope")
        self.assertEqual(failure.exception.args, ("trial_evidence_dir_unavailable",))
        self.assertEqual({field: suite["metrics"][field] for field in ("admit_read_total", "deny_total", "sensitive_path_denied_total", "binding_mismatch_total")}, {field: report["metrics"][field] for field in ("admit_read_total", "deny_total", "sensitive_path_denied_total", "binding_mismatch_total")})

    def test_second_trial_needs_fresh_decisions_and_never_reuses_a_bundle(self):
        first, first_records, _ = self.run_trial("trial-1")
        calls = []
        original = PolicyEnforcementPoint.enforce_read
        def counting(pep, *args): calls.append(args[0]["decision_id"]); return original(pep, *args)
        with patch.object(PolicyEnforcementPoint, "enforce_read", counting): second, second_records, _ = self.run_trial("trial-2")
        self.assertEqual(len(calls), len(set(calls)), "each admitted read consumes its own fresh decision")
        ids = lambda records: {record["bundle"]["bundle_id"] for record in records if record["bundle"] is not None}
        self.assertTrue(ids(first_records).isdisjoint(ids(second_records)), "a persisted bundle is evidence, never a reusable grant")
        self.assertNotIn(first["trial_id"], json.dumps(second)); self.assertEqual(len(list(self.evidence.rglob("*.json"))), 8, "bundles are never overwritten")

    def test_failures_are_redacted_and_source_boundaries_hold(self):
        source = (ROOT / "hooks/run-local-evidence-trial.py").read_text().lower()
        for forbidden in ("import subprocess", "from subprocess", "socket", "urllib", "http.client", "requests", "docker", "mcp", "environ", "getenv", "os.system", "shell", "logical_replay", "enforce_read", "decide("):
            self.assertNotIn(forbidden, source, forbidden)
        with patch.object(trial, "TRUSTED_REVISION", "no-such-revision"):
            output = io.StringIO()
            with redirect_stdout(output): code = trial.main(["--trial-id", "trial-broken", "--no-write"])
        self.assertEqual(code, 1); self.assertIn("workspace_revision_unavailable", output.getvalue()); self.assertIn("trial_suite_expectation_failed", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue()); self.assert_redacted(output.getvalue())
        self.assertFalse(self.trials.exists())
        output = io.StringIO()
        with redirect_stdout(output): self.assertEqual(trial.main(["--trial-id", "../escape"]), 1)
        self.assertEqual(output.getvalue().strip(), "invalid_trial_id")
        process = subprocess.run([__import__("sys").executable, str(ROOT / "hooks/run-local-evidence-trial.py"), "--evidence-dir", str(self.evidence / "missing")], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual((process.returncode, process.stdout.strip()), (1, "trial_evidence_dir_unavailable"))


if __name__ == "__main__": unittest.main(verbosity=2)
