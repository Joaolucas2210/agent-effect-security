"""External assessments bind to a session without rewriting its evidence."""
import copy
import json
import unittest
from pathlib import Path

from integration.session_trial import _hash as report_hash
from integration.task_evaluation import (
    _hash,
    build_task_evaluation,
    verify_task_evaluation,
)
from jsonschema import Draft7Validator


class TaskEvaluationTest(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((Path(__file__).parents[1] / "integration/v2/examples/session-trial-report.json").read_text())["valid/provenance.json"]

    def build(self, **changes):
        values = {"evaluator_id": "human-review", "evaluator_version": "1.0", "evaluated_revision_sha": "c" * 40,
                  "task_outcome": "success", "result_sha256": "d" * 64, "created_at": "2026-10-04T00:00:00Z"}
        return build_task_evaluation(self.report, **{**values, **changes})

    def test_outcomes_preserve_report_and_require_result_evidence(self):
        before = copy.deepcopy(self.report)
        for outcome in ("success", "failure"):
            record = self.build(task_outcome=outcome)
            self.assertTrue(verify_task_evaluation(record, self.report))
            self.assertEqual(record["task_outcome"], outcome)
            with self.assertRaises(ValueError):
                self.build(task_outcome=outcome, result_sha256=None)
        self.assertTrue(verify_task_evaluation(self.build(task_outcome="skipped", result_sha256=None), self.report))
        with self.assertRaises(ValueError):
            self.build(task_outcome="skipped")
        self.assertEqual(before, self.report)
        self.assertIsNone(self.report["task_outcome"])

    def test_digest_and_cross_session_binding(self):
        record = self.build()
        for field, value in (("task_outcome", "failure"), ("report_sha256", "0" * 64),
                             ("acceptance_sha256", "0" * 64), ("task_id", "other"),
                             ("session_id", "other"), ("trial_id", "other")):
            changed = {**record, field: value}
            self.assertFalse(verify_task_evaluation(changed, self.report))
            if field != "task_outcome":
                changed["verification"] = {"canonicalization": "json-c14n-v1", "evaluation_sha256": _hash(changed)}
                self.assertFalse(verify_task_evaluation(changed, self.report), "a fresh digest cannot repair cross-session bindings")
        other = copy.deepcopy(self.report)
        other["provenance"]["revision_sha"] = "0" * 40
        other["verification"]["report_sha256"] = report_hash(other)
        self.assertFalse(verify_task_evaluation(record, other))

    def test_closed_private_safe_inputs_and_missing_provenance(self):
        for values in ({"evaluator_id": "/private/reviewer"}, {"evaluator_version": "name@example.com"},
                       {"evaluated_revision_sha": "HEAD"}, {"result_sha256": "raw log"},
                       {"task_outcome": "unknown"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.build(**values)
        record = self.build()
        record["raw_log"] = "private"
        self.assertFalse(verify_task_evaluation(record, self.report))
        self.assertFalse(verify_task_evaluation(None, self.report))
        del self.report["provenance"]
        with self.assertRaises(ValueError):
            self.build()

    def test_contract_examples_and_normative_oracle(self):
        root = Path(__file__).parents[1] / "integration/v2"
        schema = json.loads((root / "schemas/task-evaluation.schema.json").read_text())
        oracle = json.loads((root / "tests/task-evaluation-normative-oracle.json").read_text())
        examples = json.loads((root / "examples/task-evaluation.json").read_text())
        Draft7Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(oracle["required_fields"]))
        self.assertEqual(set(examples), set(oracle["examples"]))
        for name, expected in oracle["examples"].items():
            self.assertEqual(Draft7Validator(schema).is_valid(examples[name]), expected["schema_valid"], name)
            self.assertEqual(verify_task_evaluation(examples[name], self.report), expected["verifies"], name)


if __name__ == "__main__":
    unittest.main()
