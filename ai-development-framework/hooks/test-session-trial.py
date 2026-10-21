"""P0-D: a session is not a bundle, and absent timing is not zero."""
import json
import copy
import importlib.util
import io
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from jsonschema import Draft7Validator

from integration.local_read_adapter import LocalReadAdapter, schemas
from integration.adapter_attempt import event_digest
from integration.session_trial import build_session_report, verify_session_report
import integration.session_trial as session_trial
import integration.local_evidence_bundle as evidence_bundle

_SPEC = importlib.util.spec_from_file_location("run_session_trial", Path(__file__).resolve().parent / "run-session-trial.py")
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)


class SessionTrialTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        for args in (("init", "-q"), ("config", "user.email", "trial@example.invalid"), ("config", "user.name", "Trial")):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)
        (self.repo / "README.md").write_text("public-example", encoding="utf-8")
        for args in (("add", "README.md"), ("commit", "-qm", "initial")):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)
        self.evidence = Path(self.temp.name) / "evidence"
        adapter = LocalReadAdapter(self.repo, "HEAD", self.evidence)
        delivered = adapter.read("session-a", "README.md", 64)
        denied = adapter.read("session-a", "../bad", 64)
        self.assertEqual((delivered["outcome"], denied["outcome"]), ("delivered", "deny"))
        self.journals = [list(map(json.loads, path.read_text().splitlines())) for path in sorted((self.evidence / "_attempts").glob("*.jsonl"))]
        self.bundle = json.loads(Path(delivered["bundle_path"]).read_text())
        self.schemas = schemas()

    def report(self, journals=None, bundles=None):
        return build_session_report("trial-a", "task-a", "session-a", self.journals if journals is None else journals, [self.bundle] if bundles is None else bundles, self.schemas, "2026-09-29T00:00:00Z")

    def test_distinct_session_attempt_bundle_and_unknown_time(self):
        report = self.report()
        self.assertTrue(verify_session_report(report))
        self.assertEqual((report["attempts_observed_total"], report["attempt_complete_total"], report["bundles_valid_total"]), (2, 2, 1))
        self.assertEqual((report["journal_invalid_total"], report["orphan_bundles_total"]), (0, 0))
        self.assertIsNone(report["task_outcome"])
        self.assertEqual(set(report["durations_ms"].values()), {None})
        self.assertNotIn("public-example", json.dumps(report))
        self.assertNotIn(str(self.repo), json.dumps(report))
        report["durations_ms"]["total"] = 0
        self.assertFalse(verify_session_report(report), "measured zero requires a new digest")

    def test_host_provenance_is_closed_hash_bound_and_optional(self):
        provenance = {"agent_name": "codex", "agent_version": "1.2.3", "revision_sha": "a" * 40, "acceptance_sha256": "b" * 64}
        report = build_session_report("trial-a", "task-a", "session-a", self.journals, [self.bundle], self.schemas, "2026-09-29T00:00:00Z", provenance=provenance)
        self.assertTrue(verify_session_report(report))
        self.assertEqual(report["provenance"], provenance)
        self.assertIsNone(report["task_outcome"])
        report["provenance"]["agent_version"] = "1.2.4"
        self.assertFalse(verify_session_report(report), "provenance is covered by the report digest")
        for changes in ({"agent_version": None}, {"agent_version": "private/path"}, {"revision_sha": "HEAD"}, {"acceptance_sha256": "bad"}, {"prompt": "private"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_session_report("trial-a", "task-a", "session-a", [], [], self.schemas, "2026-09-29T00:00:00Z", provenance={**provenance, **changes})
        self.assertNotIn("provenance", self.report())

    def test_cli_provenance_requires_all_fields_without_writing_on_failure(self):
        arguments = ["--evidence-dir", str(self.evidence), "--trial-id", "trial-a", "--task-id", "task-a", "--session-id", "session-a", "--no-write"]
        metadata = ["--agent-name", "codex", "--agent-version", "1.2.3", "--revision-sha", "a" * 40, "--acceptance-sha256", "b" * 64]
        with redirect_stdout(io.StringIO()), patch.object(runner, "persist_report") as persist:
            self.assertEqual(runner.main(arguments + metadata), 0)
            self.assertEqual(runner.main(arguments[:-1] + metadata[:2]), 1)
            persist.assert_not_called()
            self.assertEqual(runner.main(arguments[:-1] + metadata), 0)
            self.assertEqual(persist.call_args.args[0]["provenance"]["revision_sha"], "a" * 40)

    def test_incomplete_duplicate_orphan_and_invalid_are_distinct(self):
        incomplete = [[self.journals[0][0]]]
        report = self.report(journals=incomplete + incomplete, bundles=[self.bundle, self.bundle])
        self.assertTrue(verify_session_report(report))
        self.assertEqual(report["attempts_observed_total"], 1)
        self.assertEqual(report["attempt_incomplete_total"], 1)
        self.assertEqual(report["journal_invalid_total"], 0)
        self.assertEqual(report["journal_duplicates_total"], 1)
        self.assertEqual(report["bundles_invalid_total"], 0)
        self.assertEqual(report["bundle_duplicates_total"], 1)
        self.assertEqual(report["orphan_bundles_total"], 1)
        no_journal = self.report(journals=[], bundles=[self.bundle])
        self.assertEqual(no_journal["coverage"], "unknown")
        self.assertEqual(no_journal["orphan_bundles_total"], 1)
        corrupted = self.report(journals=[[{"invalid": True}]], bundles=[{"invalid": True}])
        self.assertEqual((corrupted["attempts_observed_total"], corrupted["journal_invalid_total"], corrupted["bundles_invalid_total"]), (0, 1, 1))

    def test_verifier_rejects_self_hashed_bad_counts_and_cross_session(self):
        report = self.report()
        report["attempts_observed_total"] = 3
        report["verification"]["report_sha256"] = session_trial._hash(report)
        self.assertFalse(verify_session_report(report))
        report = self.report()
        report["raw_path"] = str(self.repo / "README.md")
        report["verification"]["report_sha256"] = session_trial._hash(report)
        self.assertFalse(verify_session_report(report))
        report = self.report()
        report["observations"].append(copy.deepcopy(report["observations"][0]))
        report["attempts_observed_total"] += 1
        report["journal_files_total"] += 1
        report["verification"]["report_sha256"] = session_trial._hash(report)
        self.assertFalse(verify_session_report(report))
        other = self.report(journals=self.journals, bundles=[self.bundle])
        self.assertTrue(verify_session_report(other))
        other_run = build_session_report("trial-a", "task-a", "session-b", self.journals, [self.bundle], self.schemas, "2026-09-29T00:00:00Z")
        self.assertEqual((other_run["attempts_observed_total"], other_run["journal_invalid_total"], other_run["bundles_invalid_total"]), (0, 0, 1))
        self.assertEqual(other_run["journal_other_session_total"], 2)

    def test_shared_journals_do_not_inflate_invalid_session_artifacts(self):
        adapter = LocalReadAdapter(self.repo, "HEAD", self.evidence)
        adapter.read("session-b", "README.md", 64)
        report = runner.collect_session(str(self.evidence), "trial-a", "task-a", "session-a")
        self.assertEqual((report["journal_files_total"], report["attempts_observed_total"], report["journal_other_session_total"], report["journal_invalid_total"]), (3, 2, 1, 0))
        self.assertTrue(verify_session_report(report))
        # A valid foreign start with a changed completion binding is still invalid evidence.
        changed = copy.deepcopy(self.journals[0])
        changed[0]["run_id"] = "session-b"
        changed[0]["event_sha256"] = event_digest(changed[0])
        changed[1]["previous_event_sha256"] = changed[0]["event_sha256"]
        changed[1]["event_sha256"] = event_digest(changed[1])
        report = self.report(journals=[changed])
        self.assertEqual((report["journal_invalid_total"], report["journal_other_session_total"]), (1, 0))

    def test_decision_counts_use_only_distinct_verified_bundles(self):
        adapter = LocalReadAdapter(self.repo, "HEAD", self.evidence)
        denied = adapter.read("session-a", "missing.md", 64)
        denied_bundle = json.loads(Path(denied["bundle_path"]).read_text())
        approval = copy.deepcopy(self.bundle)
        approval.update(decision_outcome="approval_required", receipt=None, read_result_digest=None, read_result_classification=None)
        approval["bundle_id"] = evidence_bundle.digest(evidence_bundle._bundle_payload(approval))
        approval["verification"]["bundle_sha256"] = evidence_bundle.digest(evidence_bundle._bundle_payload(approval, include_id=True))
        report = self.report(bundles=[self.bundle, self.bundle, denied_bundle, approval, {"invalid": True}])
        self.assertEqual(report["decisions"], {"total": 3, "admit_read": 2, "deny": 0, "approval_required": 1, "runtime_delivered": 1, "runtime_denied": 1})
        self.assertTrue(verify_session_report(report))
        report["decisions"]["runtime_delivered"] = 2
        report["verification"]["report_sha256"] = session_trial._hash(report)
        self.assertFalse(verify_session_report(report))

    def test_conflicting_duplicate_journals_never_select_a_success_by_file_order(self):
        original = next(events for events in self.journals if events[1]["payload"]["bundle_id"] is not None)
        for journals in ([original, original[:1]], [original[:1], original]):
            report = self.report(journals=journals)
            self.assertEqual((report["attempts_observed_total"], report["journal_duplicates_total"], report["attempt_invalid_total"], report["attempt_complete_total"]), (1, 1, 1, 0))
            self.assertEqual(report["orphan_bundles_total"], 1)
            self.assertTrue(verify_session_report(report))
        corrupted = copy.deepcopy(original)
        corrupted[1]["event_sha256"] = "0" * 64
        reports = [self.report(journals=journals) for journals in ([original, corrupted], [corrupted, original])]
        self.assertEqual(reports[0], reports[1], "corrupt copies must not change counters by file order")
        self.assertEqual((reports[0]["journal_duplicates_total"], reports[0]["journal_invalid_total"], reports[0]["attempt_invalid_total"]), (0, 1, 1))
        self.assertTrue(verify_session_report(reports[0]))

    def test_new_counters_cannot_hide_invalid_artifacts_and_legacy_reports_verify(self):
        report = self.report()
        for field in ("journal_duplicates_total", "journal_other_session_total", "bundle_duplicates_total"):
            changed = copy.deepcopy(report)
            changed[field] = 1
            changed["verification"]["report_sha256"] = session_trial._hash(changed)
            self.assertFalse(verify_session_report(changed), field)
            del report[field]
        del report["decisions"]
        del report["timings"]
        report["verification"]["report_sha256"] = session_trial._hash(report)
        self.assertTrue(verify_session_report(report), "older v2 reports remain readable")

    def test_closed_contract_examples_and_normative_oracle(self):
        root = Path(__file__).resolve().parent.parent / "integration/v2"
        schema = json.loads((root / "schemas/session-trial-report.schema.json").read_text())
        oracle = json.loads((root / "tests/session-trial-normative-oracle.json").read_text())
        Draft7Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(oracle["required_fields"]))
        self.assertEqual(set(schema["properties"]) - set(schema["required"]), set(oracle["optional_fields"]))
        self.assertEqual(schema["definitions"]["duration"], {"type": ["integer", "null"], "minimum": 0})
        examples = json.loads((root / "examples/session-trial-report.json").read_text())
        self.assertEqual(set(examples), set(oracle["examples"]))
        for name, expected in oracle["examples"].items():
            report = examples[name]
            self.assertEqual(Draft7Validator(schema, registry=session_trial._REGISTRY).is_valid(report), expected["schema_valid"], name)
            self.assertEqual(verify_session_report(report), expected["verifies"], name)

    def test_all_conflicting_references_are_excluded_from_correlation(self):
        original = next(events for events in self.journals if events[1]["payload"]["bundle_id"] is not None)
        duplicate = copy.deepcopy(original)
        for event in duplicate:
            event["attempt_id"] = "0" * 32 if original[0]["attempt_id"] != "0" * 32 else "1" * 32
        duplicate[0]["event_sha256"] = event_digest(duplicate[0])
        duplicate[1]["previous_event_sha256"] = duplicate[0]["event_sha256"]
        duplicate[1]["event_sha256"] = event_digest(duplicate[1])
        report = self.report(journals=[original, duplicate])
        self.assertTrue(verify_session_report(report))
        self.assertEqual(report["correlation_conflict_total"], 2)
        self.assertEqual(report["orphan_bundles_total"], 1)
        self.assertEqual({item["bundle_status"] for item in report["observations"]}, {"conflict"})
        # A fresh hash cannot turn either conflicting reference into verified evidence.
        report["observations"][0]["bundle_status"] = "verified"
        report["correlation_conflict_total"] = 1
        report["orphan_bundles_total"] = 0
        report["verification"]["report_sha256"] = session_trial._hash(report)
        self.assertFalse(verify_session_report(report))

    def test_fifo_evidence_is_invalid_without_blocking_collection(self):
        import os
        os.mkfifo(self.evidence / "session-a" / "pipe.json")
        os.mkfifo(self.evidence / "_attempts" / "pipe.jsonl")
        command = [sys.executable, str(Path(__file__).parent / "run-session-trial.py"),
                   "--evidence-dir", str(self.evidence), "--trial-id", "trial-a",
                   "--task-id", "task-a", "--session-id", "session-a", "--no-write"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout)
        report = runner.collect_session(str(self.evidence), "trial-a", "task-a", "session-a")
        self.assertEqual((report["bundles_invalid_total"], report["journal_invalid_total"]), (1, 1))

    def test_closed_directory_reader_and_redacted_cli(self):
        report = runner.collect_session(str(self.evidence), "trial-a", "task-a", "session-a")
        self.assertTrue(verify_session_report(report))
        self.assertEqual((report["attempts_observed_total"], report["bundles_valid_total"]), (2, 1))
        target = runner.persist_report(report, Path(self.temp.name) / "trials")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertNotIn("public-example", target.read_text())
        with self.assertRaises(FileExistsError):
            runner.persist_report(report, target.parent)
        (self.evidence / "session-a" / "linked.json").symlink_to(self.repo / "README.md")
        linked = runner.collect_session(str(self.evidence), "trial-a", "task-a", "session-a")
        self.assertEqual(linked["bundles_invalid_total"], 1)
        alias = Path(self.temp.name) / "linked-evidence"
        alias.symlink_to(self.evidence, target_is_directory=True)
        with self.assertRaises(ValueError):
            runner.collect_session(str(alias), "trial-a", "task-a", "session-a")
        output = io.StringIO()
        with redirect_stdout(output):
            code = runner.main(["--evidence-dir", str(self.evidence / "missing"), "--trial-id", "trial-a", "--task-id", "task-a", "--session-id", "session-a", "--no-write"])
        self.assertEqual((code, output.getvalue().strip()), (1, "session_trial_failed"))
        self.assertNotIn(str(self.evidence), output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
