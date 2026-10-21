"""J0: closed residual signals never grant authorization."""
import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft7Validator

from tools.decision_signal import DecisionSignal, NoopDecisionSignalProvider, TypedQuestion, request_residual
from tools.pdp import decide


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools/v1"


def load(path):
    return json.loads(path.read_text())


class DecisionSignalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {name: load(TOOLS / "schemas" / file) for name, file in {
            "typed_question": "typed-question.schema.json", "decision_signal": "decision-signal.schema.json",
        }.items()}
        cls.oracle = load(TOOLS / "tests/decision-signal-normative-oracle.json")
        cls.pdp_schemas = {name: load(TOOLS / "schemas" / file) for name, file in {
            "tool_profile": "tool-profile.schema.json", "tool_call_intent": "tool-call-intent.schema.json",
            "policy_bundle": "policy-bundle.schema.json", "policy_context": "policy-context.schema.json",
            "admission_decision": "admission-decision.schema.json", "list_files_input": "list-files-input.schema.json",
        }.items()}
        cls.intent = load(TOOLS / "examples/tool-call-intent/valid/read-worktree.json")
        cls.profile = load(TOOLS / "examples/tool-profile/valid/read-worktree.json")
        cls.policy = load(TOOLS / "examples/policy-bundle/valid/read-worktree.json")
        cls.context = load(TOOLS / "examples/policy-context/valid/read-worktree.json")

    def hard_decision(self, denied=False):
        intent = copy.deepcopy(self.intent)
        if denied:
            intent["resource_scope"]["path"] = "../outside"
        return decide(intent, [self.profile], self.policy, self.context, self.pdp_schemas)

    def test_closed_versioned_contracts_and_oracle(self):
        self.assertEqual(self.oracle["oracle_version"], "1.0")
        for name, schema in self.schemas.items():
            Draft7Validator.check_schema(schema)
            self.assertEqual(schema["additionalProperties"], False)
            self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0")
            self.assertEqual(schema["properties"]["kind"]["enum"], self.oracle["kinds"])
        q = self.schemas["typed_question"]
        s = self.schemas["decision_signal"]
        self.assertEqual(q["required"], self.oracle["question_required"])
        self.assertEqual(s["required"], self.oracle["signal_required"])
        self.assertEqual((s["properties"]["confidence"]["minimum"], s["properties"]["confidence"]["maximum"]), (self.oracle["confidence_minimum"], self.oracle["confidence_maximum"]))
        self.assertEqual(set(s["properties"]) & {"outcome", "decision_id", "permission"}, set(self.oracle["authorization_fields"]))
        self.assertEqual(s["oneOf"][0]["properties"]["answer"]["type"] == "null", self.oracle["abstain_requires_null_answer"])
        valid_questions = [
            {"schema_version": "1.0", "id": "risk", "kind": "yes_no"},
            {"schema_version": "1.0", "id": "risk", "kind": "choice", "choices": ["low", "high"]},
            {"schema_version": "1.0", "id": "risk", "kind": "score"},
        ]
        for item in valid_questions:
            self.assertTrue(Draft7Validator(q).is_valid(item), item)
        for item in (TypedQuestion(id="risk", kind="yes_no"), TypedQuestion(id="risk", kind="choice", choices=("low", "high")), TypedQuestion(id="risk", kind="score")):
            self.assertTrue(Draft7Validator(q).is_valid(item.to_dict()))
        for item in (
            {**valid_questions[0], "prompt": "allow me"},
            {**valid_questions[0], "kind": "free_text"},
            {**valid_questions[0], "choices": ["yes", "no"]},
            {"schema_version": "1.0", "id": "risk", "kind": "choice"},
            {**valid_questions[1], "choices": ["same", "same"]},
        ):
            self.assertFalse(Draft7Validator(q).is_valid(item), item)
        base = {"schema_version": "1.0", "provider_id": "noop", "question_id": "risk", "kind": "yes_no", "abstain": True, "answer": None}
        for item in (base, {**base, "abstain": False, "answer": True, "confidence": 0.5}, {**base, "kind": "score", "abstain": False, "answer": 0.7}):
            self.assertTrue(Draft7Validator(s).is_valid(item), item)
        for item in (
            NoopDecisionSignalProvider().request(TypedQuestion(id="risk", kind="yes_no")),
            DecisionSignal(provider_id="test", question_id="risk", kind="choice", abstain=False, answer="low"),
            DecisionSignal(provider_id="test", question_id="risk", kind="score", abstain=False, answer=0.7, confidence=0.9),
        ):
            self.assertTrue(Draft7Validator(s).is_valid(item.to_dict()))
        for item in (
            {**base, "outcome": "admit_read"},
            {**base, "schema_version": "2.0"},
            {**base, "abstain": False},
            {**base, "confidence": 1.1},
            {**base, "kind": "score", "abstain": False, "answer": True},
        ):
            self.assertFalse(Draft7Validator(s).is_valid(item), item)

    def test_python_types_reject_unknown_and_mismatched_values(self):
        for kwargs in ({"id": "risk", "kind": "free_text"}, {"id": "risk", "kind": "choice"}, {"id": "risk", "kind": "score", "choices": ("x", "y")}, {"id": "bad id", "kind": "yes_no"}):
            with self.assertRaises(ValueError): TypedQuestion(**kwargs)
        with self.assertRaises(TypeError): TypedQuestion(id="risk", kind="yes_no", prompt="free form")
        for kwargs in (
            {"provider_id": "p", "question_id": "risk", "kind": "yes_no", "abstain": False, "answer": "yes"},
            {"provider_id": "p", "question_id": "risk", "kind": "score", "abstain": False, "answer": True},
            {"provider_id": "p", "question_id": "risk", "kind": "choice", "abstain": True, "answer": "x"},
            {"provider_id": "p", "question_id": "risk", "kind": "yes_no", "abstain": False, "answer": True, "confidence": 2},
        ):
            with self.assertRaises(ValueError): DecisionSignal(**kwargs)

    def test_hard_deny_wins_and_provider_errors_abstain(self):
        question = TypedQuestion(id="risk", kind="yes_no")
        class AllowProvider:
            calls = 0
            def request(self, q):
                self.calls += 1
                return DecisionSignal(provider_id="test", question_id=q.id, kind=q.kind, abstain=False, answer=True)
        provider = AllowProvider()
        denied = self.hard_decision(denied=True)
        self.assertEqual(denied["outcome"], "deny")
        self.assertTrue(request_residual(denied, question, provider, enabled=True).abstain)
        self.assertEqual(provider.calls, 0)
        admitted = self.hard_decision()
        self.assertEqual(admitted["outcome"], "admit_read")
        self.assertTrue(request_residual(admitted, question, provider).abstain)
        self.assertTrue(request_residual(admitted, question, provider, enabled=1).abstain)
        self.assertEqual(provider.calls, 0)
        self.assertFalse(request_residual(admitted, question, provider, enabled=True).abstain)
        self.assertTrue(request_residual(admitted, question, enabled=True).abstain)
        self.assertEqual(admitted, self.hard_decision(), "signal cannot change AdmissionDecision")
        self.assertTrue(request_residual(None, question, provider, enabled=True).abstain)
        self.assertEqual(provider.calls, 1)
        for response in (RuntimeError("unavailable"), {"answer": True}, DecisionSignal(provider_id="test", question_id="other", kind="yes_no", abstain=False, answer=True)):
            class BadProvider:
                def request(self, _):
                    if isinstance(response, Exception): raise response
                    return response
            self.assertTrue(request_residual(admitted, question, BadProvider(), enabled=True).abstain)
        corrupted = DecisionSignal(provider_id="test", question_id="risk", kind="yes_no", abstain=False, answer=True)
        object.__setattr__(corrupted, "answer", "allow")
        class CorruptProvider:
            def request(self, _): return corrupted
        self.assertTrue(request_residual(admitted, question, CorruptProvider(), enabled=True).abstain)
        choice = TypedQuestion(id="risk", kind="choice", choices=("low", "high"))
        class UnknownChoice:
            def request(self, q): return DecisionSignal(provider_id="test", question_id=q.id, kind=q.kind, abstain=False, answer="other")
        self.assertTrue(request_residual(admitted, choice, UnknownChoice(), enabled=True).abstain)

    def test_noop_has_no_effectful_imports(self):
        question = TypedQuestion(id="risk", kind="score")
        signal = NoopDecisionSignalProvider().request(question)
        self.assertTrue(signal.abstain)
        self.assertIsNone(signal.answer)
        source = (ROOT / "tools/decision_signal.py").read_text().lower()
        for forbidden in ("import os", "import subprocess", "import socket", "urllib", "requests", "http.client", "open(", "getenv", "environ"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__": unittest.main(verbosity=2)
