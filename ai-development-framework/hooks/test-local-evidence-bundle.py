"""H4-01 independent contracts, composition, and pure-offline verification tests."""
import builtins
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft7Validator


ROOT = Path(__file__).resolve().parent.parent
import integration.local_evidence_bundle as evidence
from integration.local_evidence_bundle import _bundle_payload, compose, digest, is_authorization, logical_replay, verify_offline
from runtime.local_read_runtime import LocalReadRuntime
from runtime.pep import PolicyEnforcementPoint
from runtime.workspace_manager import WorkspaceManager


def load(path): return json.loads(path.read_text())
def rehash(value, field): value[field] = digest({key: item for key, item in value.items() if key != field})


class CountingPEP:
    def __init__(self, pep): self.pep, self.calls = pep, 0
    def enforce_read(self, *args): self.calls += 1; return self.pep.enforce_read(*args)


class CountingRuntime(LocalReadRuntime):
    def __init__(self, policy): super().__init__(policy); self.calls = 0
    def read(self, *args): self.calls += 1; return super().read(*args)


class LocalEvidenceBundleTest(unittest.TestCase):
    declared = {"oracle", "fixtures", "admit_read", "deny_zero_calls", "taint", "bindings", "hashes", "receipt", "read_digest", "required", "unknown", "forbidden_data", "not_authorization", "replay", "offline_purity", "source_boundaries", "compatibility"}
    executed, skipped, failed = set(), set(), set()

    @classmethod
    def setUpClass(cls):
        h2 = ROOT / "tools/v1/schemas"; h3 = ROOT / "runtime/v1/schemas"; h4 = ROOT / "integration/v1/schemas"
        names = {"tool_profile": h2 / "tool-profile.schema.json", "tool_call_intent": h2 / "tool-call-intent.schema.json", "policy_bundle": h2 / "policy-bundle.schema.json", "policy_context": h2 / "policy-context.schema.json", "admission_decision": h2 / "admission-decision.schema.json", "list_files_input": h2 / "list-files-input.schema.json", "runtime_workspace_descriptor": h3 / "runtime-workspace-descriptor.schema.json", "runtime_audit_receipt": h3 / "runtime-audit-receipt.schema.json", "read_result": h3 / "read-result.schema.json", "adapter_request": h4 / "adapter-request.schema.json", "evidence_bundle": h4 / "evidence-bundle.schema.json"}
        cls.schemas = {name: load(path) for name, path in names.items()}
        for schema in cls.schemas.values(): Draft7Validator.check_schema(schema)
        cls.oracle = load(ROOT / "integration/v1/tests/normative-oracles.json")

    @classmethod
    def tearDownClass(cls):
        missing = cls.declared - cls.executed - cls.skipped - cls.failed
        print(f"matrix declared: {len(cls.declared)}\nmatrix executed: {len(cls.executed)}\nmissing: {len(missing)}\nskipped: {len(cls.skipped)}\nfailed: {len(cls.failed)}")

    def mark(self, name): self.executed.add(name)

    def repo(self):
        temp = tempfile.TemporaryDirectory(); source = Path(temp.name) / "source"; source.mkdir()
        for args in (("init", "-q"), ("config", "user.email", "h4@example.invalid"), ("config", "user.name", "H4")):
            subprocess.run(["git", "-C", str(source), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        target = source / "docs/readme.md"; target.parent.mkdir(); target.write_text("allowed")
        subprocess.run(["git", "-C", str(source), "add", "."], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "-C", str(source), "commit", "-qm", "initial"], check=True, stdout=subprocess.PIPE)
        return temp, source

    def request(self, descriptor, deny=False):
        base = ROOT / "tools/v1/examples"
        profile = load(base / "tool-profile/valid/read-worktree.json"); policy = load(base / "policy-bundle/valid/read-worktree.json")
        context = load(base / "policy-context/valid/read-worktree.json"); intent = load(base / "tool-call-intent/valid/read-worktree.json")
        scope, budget = {"kind": "filesystem", "path": "docs/readme.md"}, 64
        profile["operations"][0].update(supported_scopes=[scope], max_risk={"level": "low", "max_output_bytes": budget}); rehash(profile, "profile_sha256")
        policy["rules"][0].update(profile_sha256=profile["profile_sha256"], allowed_scopes=[scope], max_output_bytes=budget); rehash(policy, "policy_sha256")
        for name in ("organizational_constraints", "repository_constraints", "mode_constraints"): context[name].update(allowed_scopes=[scope], max_output_bytes=budget)
        context["resolved_run_config_ref"]["run_id"] = "run-h4-01"; context["policy_ref"] = {"policy_id": policy["policy_id"], "policy_sha256": policy["policy_sha256"]}
        if deny: context["runtime_capability"]["demonstrated"] = False
        intent.update(run_id="run-h4-01", task_ref=descriptor["snapshot_digest"], resource_scope=scope, arguments={"path": scope["path"]}, requested_budget={"max_output_bytes": budget}, policy_context_ref=copy.deepcopy(context["policy_ref"]))
        intent["tool_ref"]["profile_sha256"] = profile["profile_sha256"]
        return {"schema_version": "1.0", "adapter_id": "local-adapter", "created_at": "2026-09-22T12:00:00Z", "intent": intent, "profiles": [profile], "policy": policy, "context": context, "workspace": descriptor, "provenance": {"adapter_version": "1.0", "kind": "local_structured_adapter"}}

    def environment(self, source):
        manager = WorkspaceManager(source, "HEAD", Path(source).parent); descriptor = manager.prepare("run-h4-01")
        runtime = CountingRuntime(load(ROOT / "runtime/v1/policies/sensitive-path-policy-v1.json"))
        return manager, descriptor, CountingPEP(PolicyEnforcementPoint(manager, runtime)), runtime

    def bundle(self):
        temp, source = self.repo(); manager, descriptor, pep, _ = self.environment(source)
        bundle = compose(self.request(descriptor), self.schemas, pep)
        self.addCleanup(temp.cleanup); self.addCleanup(manager.cleanup, descriptor["workspace_id"])
        return bundle, pep

    def reseal(self, bundle):
        bundle["bundle_id"] = digest(_bundle_payload(bundle)); bundle["verification"]["bundle_sha256"] = digest(_bundle_payload(bundle, include_id=True))

    def test_oracle_precedes_scenarios(self):
        self.mark("oracle")
        self.assertEqual(self.oracle["coverage_status"], "complete")
        self.assertTrue((ROOT.parent / self.oracle["source"]["adr"]).is_file())
        for contract, spec in self.oracle["contracts"].items():
            schema = self.schemas["adapter_request" if contract == "AdapterRequest" else "evidence_bundle"]
            self.assertFalse(schema["additionalProperties"]); self.assertEqual(spec["closed"], True)
            if "required_fields" in spec: self.assertEqual(set(schema["required"]), set(spec["required_fields"]))
            for field in spec.get("forbidden_fields", []): self.assertNotIn(field, schema["properties"])
        self.assertEqual(self.oracle["canonicalization"]["algorithm"], "sha256")

    def test_fixtures_validate_before_dynamic_cases(self):
        self.mark("fixtures")
        root = ROOT / "integration/v1/examples"
        self.assertTrue(Draft7Validator(self.schemas["adapter_request"]).is_valid(load(root / "adapter-request/valid/minimum.json")))
        self.assertFalse(Draft7Validator(self.schemas["adapter_request"]).is_valid(load(root / "adapter-request/invalid/prompt.json")))
        self.assertTrue(Draft7Validator(self.schemas["evidence_bundle"]).is_valid(load(root / "evidence-bundle/valid/minimum.json")))
        self.assertFalse(Draft7Validator(self.schemas["evidence_bundle"]).is_valid(load(root / "evidence-bundle/invalid/unknown.json")))

    def test_admit_bundle_is_valid_tainted_and_portable(self):
        self.mark("admit_read"); self.mark("taint")
        bundle, pep = self.bundle()
        self.assertEqual(pep.calls, 1); self.assertTrue(verify_offline(bundle, self.schemas)); self.assertEqual(bundle["read_result_classification"], "untrusted_workspace_file")
        self.assertNotIn("allowed", json.dumps(bundle)); self.assertNotIn("canonical_root", json.dumps(bundle))

    def test_deny_never_calls_pep(self):
        self.mark("deny_zero_calls")
        temp, source = self.repo(); manager, descriptor, pep, runtime = self.environment(source)
        try:
            bundle = compose(self.request(descriptor, deny=True), self.schemas, pep)
            self.assertEqual((bundle["decision_outcome"], pep.calls, runtime.calls), ("deny", 0, 0)); self.assertTrue(verify_offline(bundle, self.schemas))
        finally: manager.cleanup(descriptor["workspace_id"]); temp.cleanup()

    def test_pre_scope_deny_is_verifiable_and_null_scope_never_admits(self):
        # invalid_scope / invalid_arguments decide before a scope exists: effective_scope is null.
        temp, source = self.repo(); manager, descriptor, pep, runtime = self.environment(source)
        try:
            request = self.request(descriptor); scope = {"kind": "filesystem", "path": "config/.env"}
            request["intent"].update(resource_scope=scope, arguments={"path": scope["path"]})
            bundle = compose(request, self.schemas, pep)
            self.assertEqual((bundle["reason_code"], bundle["effective_scope"], pep.calls), ("invalid_scope", None, 0)); self.assertTrue(verify_offline(bundle, self.schemas))
        finally: manager.cleanup(descriptor["workspace_id"]); temp.cleanup()
        admitted, _ = self.bundle(); admitted["effective_scope"] = None; self.reseal(admitted)
        self.assertFalse(verify_offline(admitted, self.schemas))

    def test_tampering_bindings_hashes_receipt_and_result_fails(self):
        bundle, _ = self.bundle()
        mutations = {"bindings": ("workspace_id", "other-workspace"), "read_digest": ("read_result_digest", "0" * 64)}
        for name, (field, value) in mutations.items():
            self.mark(name); invalid = copy.deepcopy(bundle); invalid[field] = value; self.reseal(invalid); self.assertFalse(verify_offline(invalid, self.schemas), name)
        self.mark("receipt"); invalid = copy.deepcopy(bundle); invalid["receipt"]["run_id"] = "other-run"; rehash(invalid["receipt"], "receipt_id"); self.reseal(invalid); self.assertFalse(verify_offline(invalid, self.schemas))
        for field, value in (("profile_sha256", "1" * 64), ("policy_sha256", "2" * 64), ("snapshot_digest", "3" * 64)):
            invalid = copy.deepcopy(bundle); invalid["receipt"][field] = value; rehash(invalid["receipt"], "receipt_id"); self.reseal(invalid); self.assertFalse(verify_offline(invalid, self.schemas), field)
        invalid = copy.deepcopy(bundle); invalid["receipt"] = None; self.reseal(invalid); self.assertFalse(verify_offline(invalid, self.schemas))
        self.mark("hashes"); invalid = copy.deepcopy(bundle); invalid["intent_digest"] = "0" * 64; self.assertFalse(verify_offline(invalid, self.schemas))

    def test_required_unknown_and_forbidden_fields_fail_closed(self):
        bundle, _ = self.bundle(); self.mark("required"); self.mark("unknown"); self.mark("forbidden_data")
        for field in self.schemas["evidence_bundle"]["required"]:
            invalid = copy.deepcopy(bundle); del invalid[field]; self.assertFalse(verify_offline(invalid, self.schemas), field)
        for field in ("prompt", "content", "physical_path", "secret"):
            invalid = copy.deepcopy(bundle); invalid[field] = "forbidden"; self.assertFalse(verify_offline(invalid, self.schemas), field)
        temp, source = self.repo(); manager, descriptor, pep, _ = self.environment(source)
        try:
            for field in ("prompt", "command", "secret", "token", "network", "content", "physical_path"):
                request = self.request(descriptor); request[field] = "forbidden"; self.assertRaises(ValueError, compose, request, self.schemas, pep)
            self.assertEqual(pep.calls, 0)
        finally: manager.cleanup(descriptor["workspace_id"]); temp.cleanup()

    def test_replay_authorization_and_offline_purity(self):
        bundle, _ = self.bundle(); self.mark("replay"); self.mark("not_authorization"); self.mark("offline_purity")
        self.assertEqual(logical_replay(bundle), logical_replay(copy.deepcopy(bundle))); self.assertFalse(is_authorization(bundle))
        original, original_decide = builtins.open, evidence.decide
        builtins.open = lambda *args, **kwargs: self.fail("offline verifier attempted I/O")
        evidence.decide = lambda *args: self.fail("offline verifier called PDP")
        try: self.assertTrue(verify_offline(bundle, self.schemas))
        finally: builtins.open, evidence.decide = original, original_decide

    def test_source_boundaries_and_existing_contract_compatibility(self):
        self.mark("source_boundaries"); self.mark("compatibility")
        source = (ROOT / "integration/local_evidence_bundle.py").read_text().lower()
        for forbidden in ("import subprocess", "import socket", "urllib", "http.client", "mcp", "docker", "os.system", "getenv", "environ", "localreadruntime", ".read("):
            self.assertNotIn(forbidden, source)
        for schema in self.schemas.values(): self.assertTrue(Draft7Validator.check_schema(schema) is None)


if __name__ == "__main__": unittest.main(verbosity=2)
