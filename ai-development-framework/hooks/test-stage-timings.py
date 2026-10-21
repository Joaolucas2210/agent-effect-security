"""P0-D: measured stages do not change read decisions or v1 evidence."""
import copy
import importlib.util
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
from jsonschema import Draft7Validator

from integration.attempt_timing import read_observed, verify_timing
import integration.attempt_timing as timing_module
import integration.local_read_adapter as adapter_module
from integration.local_read_adapter import LocalReadAdapter, schemas
from integration.local_evidence_bundle import verify_offline
from integration.read_gate_host import read_adapter
from integration.session_trial import verify_session_report

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("session_runner", ROOT / "hooks/run-session-trial.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class StageTimingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.repo = self.repo.resolve()
        for args in (("init", "-q"), ("config", "user.email", "timing@example.invalid"), ("config", "user.name", "Timing")):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)
        (self.repo / "readme.md").write_text("public-example")
        for args in (("add", "."), ("commit", "-qm", "initial")):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)
        self.evidence = Path(self.temp.name) / "evidence"
        self.adapter = LocalReadAdapter(self.repo, "HEAD", self.evidence)

    def read(self, path="readme.md"):
        return read_observed(self.adapter, "session-time", path, 64, self.evidence)

    def records(self):
        return [json.loads(p.read_text()) for p in sorted((self.evidence / "_timings").glob("*.json"))]

    def report(self):
        return runner.collect_session(str(self.evidence), "trial-time", "task-time", "session-time")

    def test_monotonic_stages_sum_only_persistence_and_total_spans_return(self):
        ticks = iter(range(0, 100_000_000, 1_000_000))
        with patch.object(timing_module.time, "monotonic_ns", side_effect=lambda: next(ticks)), patch.object(timing_module.time, "time", side_effect=AssertionError("wall clock must not measure stages")):
            result = self.read()
        self.assertEqual(result["content"], "public-example")
        record, = self.records()
        self.assertTrue(verify_timing(record))
        durations = record["durations_ms"]
        self.assertEqual({durations[s] for s in ("prepare", "decision", "read", "cleanup")}, {1})
        self.assertEqual(durations["persistence"], 3)
        self.assertGreater(durations["total"], sum(durations[s] for s in durations if s != "total"))
        self.assertEqual(record["return_state"], "returned")
        self.assertNotIn("public-example", json.dumps(record))
        self.assertNotIn(str(self.repo), json.dumps(record))
        bundle = json.loads(Path(result["bundle_path"]).read_text())
        self.assertTrue(verify_offline(bundle, schemas()))
        self.assertNotIn("durations_ms", bundle)
        ticks = iter(range(0, 60_000_000, 600_000))
        with patch.object(timing_module.time, "monotonic_ns", side_effect=lambda: next(ticks)):
            self.read()
        self.assertIn(1, [r["durations_ms"]["persistence"] for r in self.records()], "sub-ms persistence spans must accumulate before rounding")

    def test_measured_zero_and_missing_stages_are_distinct(self):
        with patch.object(timing_module.time, "monotonic_ns", return_value=0):
            self.read()
            self.read("/invalid")
        records = self.records()
        measured = next(r for r in records if r["durations_ms"]["read"] is not None)
        missing = next(r for r in records if r["durations_ms"]["read"] is None)
        self.assertEqual(set(measured["durations_ms"].values()), {0})
        self.assertEqual((missing["durations_ms"]["persistence"], missing["durations_ms"]["total"]), (0, 0))
        self.assertIsNone(missing["durations_ms"]["prepare"])
        report = self.report()
        self.assertTrue(verify_session_report(report))
        self.assertEqual(report["timings"]["stages"]["read"], {"count": 1, "sum": 0, "min": 0, "max": 0})
        self.assertEqual(set(report["durations_ms"].values()), {None}, "attempt durations are not session wall time")

    def test_prepare_read_cleanup_and_journal_failures_keep_their_outcomes(self):
        cases = [
            ("WorkspaceManager", "prepare", RuntimeError("workspace_revision_unavailable"), "workspace_revision_unavailable", "prepare"),
            ("LocalReadRuntime", "read", OSError("private-example"), "adapter_failed", "read"),
            ("WorkspaceManager", "cleanup", OSError("private-example"), "workspace_worktree_cleanup_failed", "cleanup"),
            ("AttemptJournal", "finish", OSError("private-example"), "attempt_evidence_failed", "persistence"),
        ]
        for owner, method, error, reason, stage in cases:
            with self.subTest(stage=stage), patch.object(getattr(adapter_module, owner), method, side_effect=error):
                result = self.read()
            self.assertEqual((result["outcome"], result["reason_code"]), ("deny", reason))
            self.assertNotIn("content", result)
        records = self.records()
        self.assertEqual(len(records), 4)
        self.assertTrue(all(verify_timing(r) for r in records))
        self.assertEqual(self.report()["timings"]["observed_total"], 4)

    def test_interruption_is_raised_and_cleanup_is_measured(self):
        with patch.object(adapter_module, "compose", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.read()
        record, = self.records()
        self.assertEqual(record["return_state"], "raised")
        self.assertIsNotNone(record["durations_ms"]["cleanup"])
        self.assertIsNone(record["durations_ms"]["decision"])
        self.assertEqual(self.report()["attempt_incomplete_total"], 1)

    def test_telemetry_failure_does_not_change_delivery_or_leak_exception(self):
        stderr = io.StringIO()
        with patch.object(timing_module, "persist_timing", side_effect=OSError("private-example")), redirect_stderr(stderr):
            result = self.read()
        self.assertEqual(result["outcome"], "delivered")
        self.assertEqual(stderr.getvalue().strip(), "adf: timing_evidence_failed")
        self.assertEqual(self.report()["timings"]["coverage"], "unknown")
        with patch.object(adapter_module, "AttemptJournal", side_effect=OSError("private-example")):
            result = self.read()
        self.assertEqual(result["reason_code"], "attempt_evidence_failed")
        self.assertEqual(self.records(), [])

    def test_host_opt_in_preserves_default_and_pdp_denial_skips_runtime(self):
        with patch.dict(os.environ, {"ADF_CAPTURE_TIMINGS": "0"}):
            result = read_adapter(self.adapter, "session-time", "readme.md", 64, self.evidence)
        self.assertEqual(result["outcome"], "delivered")
        self.assertEqual(self.records(), [])
        original = adapter_module.build_request
        def mismatch(*args, **kwargs):
            request = original(*args, **kwargs)
            request["context"]["resolved_run_config_ref"]["run_id"] = "other-session"
            return request
        with patch.dict(os.environ, {"ADF_CAPTURE_TIMINGS": "1"}), patch.object(adapter_module, "build_request", mismatch):
            result = read_adapter(self.adapter, "session-time", "readme.md", 64, self.evidence)
        self.assertEqual(result["reason_code"], "run_binding_mismatch")
        record, = self.records()
        self.assertIsNotNone(record["durations_ms"]["decision"])
        self.assertIsNone(record["durations_ms"]["read"])

    def test_both_native_gates_and_mcp_capture_only_with_host_opt_in(self):
        gates = []
        for filename in ("claude-code-read-gate.py", "codex-bash-read-gate.py"):
            spec = importlib.util.spec_from_file_location(filename, ROOT / "hooks" / filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            gates.append(module)
        env = {"ADF_TRUSTED_REPOSITORY": str(self.repo), "ADF_TRUSTED_REVISION": "HEAD", "ADF_EVIDENCE_DIR": str(self.evidence), "ADF_MAX_OUTPUT_BYTES": "64", "ADF_RUN_ID": "session-time", "ADF_CAPTURE_TIMINGS": "1"}
        for module, tool, key, argument in ((gates[0], "Read", "file_path", str(self.repo / "readme.md")), (gates[1], "Bash", "command", "cat " + str(self.repo / "readme.md"))):
            payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "session-time", "tool_input": {key: argument}}
            with patch.dict(os.environ, env, clear=True):
                response = module.gate(payload)
                self.assertTrue(response == {} or response["hookSpecificOutput"]["permissionDecision"] == "allow")
                injected = {**payload, "tool_input": {**payload["tool_input"], "ADF_CAPTURE_TIMINGS": "1"}}
                self.assertEqual(module.gate(injected)["hookSpecificOutput"]["permissionDecision"], "deny")
        request = adapter_module.build_request({"snapshot_digest": "a" * 64}, "session-time", "readme.md", 64)
        policy = {"schema_version": "1.0", **{key: request[key] for key in ("profiles", "policy", "context")}}
        policy_file = Path(self.temp.name) / "policy.json"
        policy_file.write_text(json.dumps(policy))
        from integration.mcp_read_server import read_snapshot
        with patch.dict(os.environ, {**env, "ADF_READ_POLICY_FILE": str(policy_file), "ADF_READ_POLICY_SHA256": adapter_module.digest(policy)}, clear=True):
            self.assertEqual(read_snapshot("readme.md"), "public-example")
        self.assertEqual(self.report()["timings"]["observed_total"], 3)

    def test_storage_hash_bindings_duplicates_and_conflicts_fail_closed(self):
        self.read()
        record, = self.records()
        path, = (self.evidence / "_timings").glob("*.json")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        with self.assertRaises(FileExistsError):
            timing_module.persist_timing(record, self.evidence)
        (path.parent / "duplicate.json").write_text(path.read_text())
        report = self.report()
        self.assertEqual((report["timings"]["observed_total"], report["timings"]["duplicates_total"]), (1, 1))
        changed = copy.deepcopy(record)
        changed["return_state"] = "raised"
        changed["verification"]["record_sha256"] = timing_module.timing_digest(changed)
        (path.parent / "conflict.json").write_text(json.dumps(changed))
        report = self.report()
        self.assertEqual((report["timings"]["observed_total"], report["timings"]["conflicts_total"]), (0, 2))
        self.assertTrue(verify_session_report(report))
        for field, value in (("start_event_sha256", "0" * 64), ("content", "private-example")):
            changed = copy.deepcopy(record)
            changed[field] = value
            changed["verification"]["record_sha256"] = timing_module.timing_digest(changed)
            (path.parent / "conflict.json").write_text(json.dumps(changed))
            self.assertGreaterEqual(self.report()["timings"]["invalid_total"], 1)
        os.mkfifo(path.parent / "pipe.json")
        (path.parent / "linked.json").symlink_to(path)
        self.assertGreaterEqual(self.report()["timings"]["invalid_total"], 3)
        for filename, field, value in (("foreign.json", "run_id", "other-session"), ("unbound.json", "attempt_id", "f" * 32)):
            changed = copy.deepcopy(record)
            changed[field] = value
            changed["verification"]["record_sha256"] = timing_module.timing_digest(changed)
            (path.parent / filename).write_text(json.dumps(changed))
        report = self.report()
        self.assertEqual((report["timings"]["observed_total"], report["timings"]["other_session_total"], report["timings"]["uncorrelated_total"]), (1, 1, 1))
        self.assertEqual(report["timings"]["stages"]["read"]["count"], 1)
        self.assertTrue(verify_session_report(report))
        linked_root = Path(self.temp.name) / "linked-root"
        linked_root.symlink_to(self.evidence)
        with self.assertRaises(OSError):
            timing_module.persist_timing(record, linked_root)
        path.parent.rename(self.evidence / "old-timings")
        (self.evidence / "_timings").symlink_to(self.evidence / "old-timings")
        with self.assertRaises(OSError):
            timing_module.persist_timing(record, self.evidence)

    def test_verifiers_reject_tampered_durations_and_summaries(self):
        self.read()
        record, = self.records()
        for value in (-1, True, 1.5, "1"):
            changed = copy.deepcopy(record)
            changed["durations_ms"]["read"] = value
            changed["verification"]["record_sha256"] = timing_module.timing_digest(changed)
            self.assertFalse(verify_timing(changed))
        report = self.report()
        report["timings"]["stages"]["read"]["count"] += 1
        import integration.session_trial as session_trial
        report["verification"]["report_sha256"] = session_trial._hash(report)
        self.assertFalse(verify_session_report(report))

    def test_timing_contract_oracle_and_examples(self):
        root = ROOT / "integration/v2"
        oracle = json.loads((root / "tests/attempt-timing-normative-oracle.json").read_text())
        schema = timing_module.TIMING_SCHEMA
        Draft7Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(oracle["required_fields"]))
        self.assertEqual(set(schema["properties"]["durations_ms"]["required"]), set(oracle["stages"]))
        self.assertEqual(schema["properties"]["return_state"]["enum"], oracle["return_states"])
        self.assertEqual(schema["properties"]["provenance"]["properties"], {key: {"const": value} for key, value in oracle["provenance"].items()})
        examples = json.loads((root / "examples/attempt-timing.json").read_text())
        self.assertEqual(set(examples), set(oracle["examples"]))
        for name, expected in oracle["examples"].items():
            record = examples[name]
            self.assertEqual(Draft7Validator(schema).is_valid(record), expected["schema_valid"])
            self.assertEqual(verify_timing(record), expected["verifies"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
