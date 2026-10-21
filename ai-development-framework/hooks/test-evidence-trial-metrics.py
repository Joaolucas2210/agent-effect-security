"""H4-01b contracts and pure aggregation tests; no runtime effects are exercised."""
import builtins
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft7Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parent.parent
import integration.evidence_trial_metrics as metrics
import integration.local_evidence_bundle as evidence


def load(path): return json.loads(path.read_text())
def sha(text): return hashlib.sha256(text.encode()).hexdigest()


def require(condition):
    if not condition:
        raise AssertionError("h4_01b_precondition_failed")


def validate_preconditions(schemas, mapping, oracle):
    require(oracle["coverage_status"] == "complete")
    require((ROOT.parent / oracle["source"]["adr"]).is_file())
    for name, spec in oracle["contracts"].items():
        schema = schemas["evidence_trial_observation" if name.endswith("Observation") else "evidence_trial_report"]
        require(schema.get("additionalProperties") is False)
        require(set(schema.get("required", ())) == set(spec["required_fields"]))
        require(all(field not in schema.get("properties", {}) for field in spec["forbidden_fields"]))
    mapping_spec = oracle["reason_code_mapping"]
    require(mapping.get("mapping_version") == mapping_spec["version"])
    require(mapping.get("categories") == mapping_spec["categories"])
    require(all(set(mapping.get(key, ())) == set(mapping_spec[key]) for key in ("h2_reason_codes", "h3_reason_codes")))
    for name, spec in oracle["types"].items():
        schema = schemas["evidence_trial_observation" if name.endswith("Observation") else "evidence_trial_report"]
        version = schema["properties"]["schema_version"]
        require(version.get("const") == spec["schema_version"]["const"] and isinstance(version.get("const"), str))
        require(all(schema["definitions"][schema["properties"][field]["$ref"].rsplit("/", 1)[-1]]["type"] == "string" for field in spec["ids"]))
        if name.endswith("Observation"):
            require(schema["properties"]["human_intervention_required"].get("type") == spec["human_intervention_required"])
            require(schema["properties"]["decision_latency_ms"].get("type") == spec["decision_latency_ms"])
        else:
            require(all(schema["properties"][field].get("type") == "integer" for field in spec["totals"]))
            latency = schema["properties"]["decision_latency_ms"]["properties"]
            require(all(latency[field].get("type") == expected for field, expected in spec["decision_latency_ms"].items()))
    examples = ROOT / "integration/v1/examples"
    registry = Registry().with_resource("evidence-bundle.schema.json", Resource.from_contents(schemas["evidence_bundle"]))
    observer = Draft7Validator(schemas["evidence_trial_observation"], registry=registry)
    reporter = Draft7Validator(schemas["evidence_trial_report"])
    require(observer.is_valid(load(examples / "evidence-trial-observation/valid/minimum.json")))
    require(not observer.is_valid(load(examples / "evidence-trial-observation/invalid/prompt.json")))
    fixture_report = load(examples / "evidence-trial-report/valid/minimum.json")
    require(reporter.is_valid(fixture_report) and metrics.verify_trial_report(fixture_report, schemas))
    require(not reporter.is_valid(load(examples / "evidence-trial-report/invalid/unknown.json")))


class EvidenceTrialMetricsTest(unittest.TestCase):
    declared = {"preconditions", "meta_contract_types", "three_trials", "decision_outcomes", "binding_categories", "sensitive_path_denied", "invalid_contract", "tampered_bundle", "invalid_receipt", "bundle_unknown", "missing_required", "duplicates", "forbidden_input", "approval_required", "unknown_outcome", "invariants", "invariants_before_hash", "report_tampering", "report_hash", "report_unknown", "self_hashed_invalid", "determinism", "report_purity", "no_effect_surfaces"}
    executed, skipped, failed = set(), set(), set()

    @classmethod
    def setUpClass(cls):
        schemas = ROOT / "integration/v1/schemas"; runtime = ROOT / "runtime/v1/schemas"
        cls.schemas = {"evidence_trial_observation": load(schemas / "evidence-trial-observation.schema.json"), "evidence_trial_report": load(schemas / "evidence-trial-report.schema.json"), "evidence_bundle": load(schemas / "evidence-bundle.schema.json"), "runtime_audit_receipt": load(runtime / "runtime-audit-receipt.schema.json")}
        for schema in cls.schemas.values(): Draft7Validator.check_schema(schema)
        cls.mapping = load(ROOT / "integration/v1/policies/evidence-metric-reason-codes-v1.json")
        cls.oracle = load(ROOT / "integration/v1/tests/evidence-trial-metrics-normative-oracle.json")
        validate_preconditions(cls.schemas, cls.mapping, cls.oracle)
        cls.preconditions_validated = True
        print("preconditions: oracle and fixtures validated before scenarios", file=sys.stderr)

    @classmethod
    def tearDownClass(cls):
        missing = cls.declared - cls.executed - cls.skipped - cls.failed
        print(f"matrix declared: {len(cls.declared)}\nmatrix executed: {len(cls.executed)}\nmissing: {len(missing)}\nskipped: {len(cls.skipped)}\nfailed: {len(cls.failed)}")

    def mark(self, *names): self.executed.update(names)
    def context(self): return {"report_id": "report-h4-01b", "created_at": "2026-09-22T12:00:00Z", "provenance": {"aggregator_version": "1.0", "kind": "local_evidence_trial_metrics"}}

    def bundle(self, label, decision_outcome="deny", h2_reason="invalid_intent", h3_reason=None):
        bundle = {"schema_version": "1.0", "bundle_id": "", "run_id": f"run-{label}", "adapter_id": "local-adapter", "created_at": "2026-09-22T12:00:00Z", "decision_id": sha(f"decision-{label}"), "decision_outcome": decision_outcome, "reason_code": h2_reason, "profile_sha256": sha(f"profile-{label}"), "policy_sha256": sha(f"policy-{label}"), "intent_digest": sha(f"intent-{label}"), "operation_id": "read", "effective_scope": {"kind": "filesystem", "path": "docs/redacted.md"}, "workspace_id": f"workspace-{label}", "snapshot_digest": sha(f"snapshot-{label}"), "read_result_digest": None, "read_result_classification": None, "receipt": None, "verification": {"verification_version": "1.0", "canonicalization": "json-c14n-v1", "bundle_sha256": ""}, "provenance": {"adapter_version": "1.0", "pdp_version": "1.0", "pep_version": "not_called", "kind": "local_evidence_composition"}}
        if decision_outcome == "admit_read":
            outcome = "delivered" if h3_reason == "read_delivered" else "deny"
            receipt = {"receipt_version": "1.0", "receipt_id": "", "decision_id": bundle["decision_id"], "run_id": bundle["run_id"], "operation_id": bundle["operation_id"], "effective_scope": bundle["effective_scope"], "profile_sha256": bundle["profile_sha256"], "policy_sha256": bundle["policy_sha256"], "workspace_id": bundle["workspace_id"], "snapshot_digest": bundle["snapshot_digest"], "outcome": outcome, "reason_code": h3_reason, "bytes_read": 1 if outcome == "delivered" else 0, "timestamp": "2026-09-22T12:00:00Z", "provenance": {"runtime_version": "1.0", "kind": "redacted_runtime_receipt"}}
            if outcome == "delivered": receipt["content_sha256"] = sha("x")
            receipt["receipt_id"] = metrics.digest({key: value for key, value in receipt.items() if key != "receipt_id"})
            projection = {"result_version": "1.0", "outcome": outcome, "reason_code": h3_reason, "bytes_read": receipt["bytes_read"], "taint": {"classification": "untrusted_workspace_file", "cannot_authorize": True}, "provenance": {"runtime_version": "1.0", "workspace_id": bundle["workspace_id"], "snapshot_digest": bundle["snapshot_digest"]}}
            if "content_sha256" in receipt: projection["content_sha256"] = receipt["content_sha256"]
            bundle.update(read_result_digest=metrics.digest(projection), read_result_classification="untrusted_workspace_file", receipt=receipt)
            bundle["provenance"]["pep_version"] = "1.0"
        payload = copy.deepcopy(bundle); payload.pop("bundle_id"); payload["verification"].pop("bundle_sha256")
        bundle["bundle_id"] = metrics.digest(payload)
        payload = copy.deepcopy(bundle); payload["verification"].pop("bundle_sha256")
        bundle["verification"]["bundle_sha256"] = metrics.digest(payload)
        self.assertTrue(evidence.verify_offline(bundle, self.schemas))
        return bundle

    def observation(self, label, bundle=None, latency=1, human=False):
        bundle = bundle or self.bundle(label)
        if bundle["decision_outcome"] == "admit_read":
            runtime_outcome, runtime_reason = bundle["receipt"]["outcome"], bundle["receipt"]["reason_code"]
        else:
            runtime_outcome, runtime_reason = "not_attempted", None
        return {"schema_version": "1.0", "observation_id": f"observation-{label}", "trial_id": f"trial-{label}", "observed_at": "2026-09-22T12:00:00Z", "evidence_bundle": bundle, "runtime_outcome": runtime_outcome, "runtime_reason_code": runtime_reason, "human_intervention_required": human, "decision_latency_ms": latency, "provenance": {"collector_version": "1.0", "kind": "local_trial_observation"}}

    def aggregate(self, observations): return metrics.aggregate_trial_observations(observations, self.context(), self.schemas, self.mapping)

    def reseal(self, bundle):
        payload = copy.deepcopy(bundle); payload.pop("bundle_id"); payload["verification"].pop("bundle_sha256")
        bundle["bundle_id"] = metrics.digest(payload)
        payload = copy.deepcopy(bundle); payload["verification"].pop("bundle_sha256")
        bundle["verification"]["bundle_sha256"] = metrics.digest(payload)

    def test_preconditions_are_validated_before_scenarios(self):
        self.mark("preconditions")
        self.assertTrue(self.preconditions_validated)

    def test_preconditions_reject_in_memory_contract_regressions(self):
        self.mark("meta_contract_types")
        mutations = (
            lambda schemas, mapping: schemas["evidence_trial_report"]["properties"]["decisions_total"].update(type="number"),
            lambda schemas, mapping: schemas["evidence_trial_observation"]["properties"]["human_intervention_required"].update(type="string"),
            lambda schemas, mapping: schemas["evidence_trial_report"].update(additionalProperties=True),
            lambda schemas, mapping: schemas["evidence_trial_report"]["required"].remove("decisions_total"),
            lambda schemas, mapping: mapping["h2_reason_codes"].pop("invalid_intent"),
        )
        for mutate in mutations:
            schemas, mapping = copy.deepcopy(self.schemas), copy.deepcopy(self.mapping)
            mutate(schemas, mapping)
            with self.assertRaises(AssertionError): validate_preconditions(schemas, mapping, self.oracle)

    def test_three_distinct_trials_preserve_verified_decisions(self):
        self.mark("three_trials", "decision_outcomes", "invariants")
        observations = [self.observation("one", self.bundle("one", "admit_read", "admit_read", "read_delivered"), 3), self.observation("two", self.bundle("two", "deny", "profile_hash_mismatch"), 5, True), self.observation("three", self.bundle("three", "deny", "invalid_intent"), 7)]
        report = self.aggregate(observations)
        self.assertTrue(metrics.verify_trial_report(report, self.schemas))
        self.assertEqual((report["trial_count"], report["decisions_total"], report["admit_read_total"], report["deny_total"]), (3, 3, 1, 2))
        self.assertEqual(report["decisions_total"], report["admit_read_total"] + report["deny_total"])
        self.assertEqual((report["binding_mismatch_total"], report["invalid_contract_total"], report["human_intervention_required_total"]), (1, 1, 1))
        self.assertEqual(report["decision_latency_ms"], {"count": 3, "sum": 15, "min": 3, "max": 7})
        self.assertNotIn("docs/redacted.md", json.dumps(report))

    def test_all_published_metric_categories_are_counted(self):
        for code, category in self.mapping["h2_reason_codes"].items():
            if category not in {"binding_mismatch", "invalid_contract"}: continue
            self.mark("binding_categories" if category == "binding_mismatch" else "invalid_contract")
            report = self.aggregate([self.observation(f"h2-{code}", self.bundle(f"h2-{code}", "deny", code))])
            self.assertEqual(report[f"{category}_total"], 1, code)
        for code, category in self.mapping["h3_reason_codes"].items():
            if category not in {"binding_mismatch", "sensitive_path_denied", "invalid_contract"}: continue
            self.mark("binding_categories" if category == "binding_mismatch" else category)
            report = self.aggregate([self.observation(f"h3-{code}", self.bundle(f"h3-{code}", "admit_read", "admit_read", code))])
            self.assertEqual(report[f"{category}_total"], 1, code)

    def test_invalid_observations_are_redacted_and_counted_only_as_invalid(self):
        valid = self.observation("valid", self.bundle("valid", "deny", "invalid_intent"))
        cases = {}
        tampered = copy.deepcopy(valid); tampered["evidence_bundle"]["workspace_id"] = "other"; cases["tampered_bundle"] = tampered
        receipt = self.observation("receipt", self.bundle("receipt", "admit_read", "admit_read", "read_delivered")); receipt["evidence_bundle"]["receipt"]["receipt_id"] = "0" * 64; self.reseal(receipt["evidence_bundle"]); cases["invalid_receipt"] = receipt
        unknown = copy.deepcopy(valid); unknown["evidence_bundle"]["unknown"] = True; self.reseal(unknown["evidence_bundle"]); cases["bundle_unknown"] = unknown
        missing = copy.deepcopy(valid); del missing["observed_at"]; cases["missing_required"] = missing
        for field in ("prompt", "code", "content", "physical_path", "physical_root", "arguments", "secret", "token", "command", "remote_host", "network"):
            forbidden = copy.deepcopy(valid); forbidden[field] = "forbidden"; cases["forbidden_input"] = forbidden
        for name, invalid in cases.items():
            self.mark(name); report = self.aggregate([valid, invalid]); self.assertEqual((report["evidence_bundle_valid_total"], report["evidence_bundle_invalid_total"], report["decisions_total"]), (1, 1, 1), name); self.assertNotIn("forbidden", json.dumps(report))

    def test_duplicate_ids_are_rejected_from_aggregation(self):
        self.mark("duplicates")
        first = self.observation("first", self.bundle("first")); duplicate_trial = self.observation("second", self.bundle("second")); duplicate_trial["trial_id"] = first["trial_id"]
        duplicate_observation = self.observation("third", self.bundle("third")); duplicate_observation["observation_id"] = first["observation_id"]
        report = self.aggregate([first, duplicate_trial, duplicate_observation])
        self.assertEqual((report["observations_total"], report["evidence_bundle_valid_total"], report["evidence_bundle_invalid_total"]), (3, 1, 2))

    def test_non_metric_outcomes_are_invalid_only(self):
        valid = self.observation("metric", self.bundle("metric"))
        approval = self.observation("approval", self.bundle("approval", "approval_required"))
        unknown = copy.deepcopy(valid); unknown["evidence_bundle"]["decision_outcome"] = "unknown"; self.reseal(unknown["evidence_bundle"])
        for name, invalid in (("approval_required", approval), ("unknown_outcome", unknown)):
            self.mark(name)
            report = self.aggregate([valid, invalid])
            self.assertEqual((report["evidence_bundle_valid_total"], report["evidence_bundle_invalid_total"], report["decisions_total"], report["admit_read_total"], report["deny_total"], report["human_intervention_required_total"]), (1, 1, 1, 0, 1, 0))
            self.assertEqual(report["decision_latency_ms"], {"count": 1, "sum": 1, "min": 1, "max": 1})

    def test_report_rejects_tampering_unknown_data_and_self_hashed_bad_math(self):
        report = self.aggregate([self.observation("report", self.bundle("report"))])
        changed = copy.deepcopy(report); changed["decisions_total"] = 0; self.mark("report_tampering"); self.assertFalse(metrics.verify_trial_report(changed, self.schemas))
        changed = copy.deepcopy(report); changed["verification"]["report_sha256"] = "0" * 64; self.mark("report_hash"); self.assertFalse(metrics.verify_trial_report(changed, self.schemas))
        changed = copy.deepcopy(report); changed["unknown"] = True; changed["verification"]["report_sha256"] = metrics.digest(metrics._report_payload(changed)); self.mark("report_unknown"); self.assertFalse(metrics.verify_trial_report(changed, self.schemas))
        changed = copy.deepcopy(report); changed["trial_count"] = 2; changed["verification"]["report_sha256"] = metrics.digest(metrics._report_payload(changed)); self.mark("self_hashed_invalid"); self.assertFalse(metrics.verify_trial_report(changed, self.schemas))

    def test_invariants_fail_before_hash_comparison(self):
        report = self.aggregate([self.observation("ordered", self.bundle("ordered"))])
        report["decisions_total"] = 0
        report["verification"]["report_sha256"] = metrics.digest(metrics._report_payload(report))
        original_digest = metrics.digest
        metrics.digest = lambda _value: self.fail("hash checked before invariants")
        try:
            self.mark("invariants_before_hash")
            self.assertFalse(metrics.verify_trial_report(report, self.schemas))
        finally:
            metrics.digest = original_digest

    def test_determinism_and_pure_verification(self):
        observations = [self.observation("deterministic", self.bundle("deterministic"), 9)]
        self.mark("determinism"); self.assertEqual(self.aggregate(observations), self.aggregate(copy.deepcopy(observations)))
        report = self.aggregate(observations); original_open, original_decide = builtins.open, evidence.decide
        builtins.open = lambda *args, **kwargs: self.fail("verifier attempted I/O")
        evidence.decide = lambda *args, **kwargs: self.fail("aggregator called PDP")
        try:
            self.mark("report_purity"); self.assertTrue(metrics.verify_trial_report(report, self.schemas)); self.assertTrue(self.aggregate(observations))
        finally:
            builtins.open, evidence.decide = original_open, original_decide

    def test_aggregator_source_has_no_effectful_surface(self):
        self.mark("no_effect_surfaces")
        source = (ROOT / "integration/evidence_trial_metrics.py").read_text().lower()
        for forbidden in ("import subprocess", "import socket", "urllib", "http.client", "mcp", "docker", "os.system", "getenv", "environ", "workspace_manager", "policyenforcementpoint", "localreadruntime", ".decide("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__": unittest.main(verbosity=2)
