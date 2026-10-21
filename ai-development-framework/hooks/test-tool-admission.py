"""Independent static-oracle and PDP tests for H2-02."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft7Validator


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools/v1"
from tools.pdp import decide


FILES = {"ToolProfile": "tool-profile", "ToolCallIntent": "tool-call-intent", "PolicyBundle": "policy-bundle", "PolicyContext": "policy-context", "AdmissionDecision": "admission-decision"}
SCHEMA_KEYS = {"ToolProfile": "tool_profile", "ToolCallIntent": "tool_call_intent", "PolicyBundle": "policy_bundle", "PolicyContext": "policy_context", "AdmissionDecision": "admission_decision", "Input": "list_files_input"}


def load(path):
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def hashed(value, field):
    value[field] = digest({key: item for key, item in value.items() if key != field})


def pointer(value, path):
    for part in path.strip("/").split("/"):
        value = value[part]
    return value


class ToolAdmissionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {key: load(TOOLS / "schemas" / filename) for key, filename in (("tool_profile", "tool-profile.schema.json"), ("tool_call_intent", "tool-call-intent.schema.json"), ("policy_bundle", "policy-bundle.schema.json"), ("policy_context", "policy-context.schema.json"), ("admission_decision", "admission-decision.schema.json"), ("list_files_input", "list-files-input.schema.json"))}
        for schema in cls.schemas.values(): Draft7Validator.check_schema(schema)
        cls.oracle = load(TOOLS / "tests/normative-oracles.json")
        cls.profile = load(TOOLS / "examples/tool-profile/valid/read-worktree.json")
        cls.policy = load(TOOLS / "examples/policy-bundle/valid/read-worktree.json")
        cls.context = load(TOOLS / "examples/policy-context/valid/read-worktree.json")
        cls.intent = load(TOOLS / "examples/tool-call-intent/valid/read-worktree.json")

    def base(self):
        return copy.deepcopy(self.intent), [copy.deepcopy(self.profile)], copy.deepcopy(self.policy), copy.deepcopy(self.context)

    def bind(self, intent, profiles, policy, context):
        for profile in profiles: hashed(profile, "profile_sha256")
        profile = profiles[0]
        for rule in policy["rules"]: rule["profile_sha256"] = profile["profile_sha256"]
        hashed(policy, "policy_sha256")
        context["policy_ref"] = {"policy_id": policy["policy_id"], "policy_sha256": policy["policy_sha256"]}
        intent["tool_ref"]["profile_sha256"] = profile["profile_sha256"]
        intent["policy_context_ref"] = copy.deepcopy(context["policy_ref"])

    def result(self, intent, profiles, policy, context):
        outcome = decide(intent, profiles, policy, context, self.schemas)
        Draft7Validator(self.schemas["admission_decision"]).validate(outcome)
        self.assertNotEqual(outcome["outcome"], "approval_required")
        return outcome

    def test_static_oracle_precedes_dynamic_mutations(self):
        oracle = self.oracle
        self.assertEqual(oracle["oracle_version"], "1.0")
        self.assertEqual(oracle["coverage_status"], "complete")
        self.assertTrue((ROOT.parent / oracle["source"]["adr"]).is_file())
        self.assertEqual(set(oracle["contracts"]), set(FILES))
        for contract, spec in oracle["contracts"].items():
            schema = self.schemas[SCHEMA_KEYS[contract]]
            self.assertEqual(spec["schema_file"], f"{FILES[contract]}.schema.json")
            for check in spec["checks"]: self.assertEqual(pointer(schema, check["pointer"]), check["expected"], f"{contract} {check['pointer']}")

    def test_fixtures_and_hashes(self):
        for contract, stem in FILES.items():
            validator = Draft7Validator(self.schemas[SCHEMA_KEYS[contract]])
            valid = next((TOOLS / "examples" / stem / "valid").glob("*.json"))
            invalid = next((TOOLS / "examples" / stem / "invalid").glob("*.json"))
            self.assertTrue(validator.is_valid(load(valid)), contract)
            self.assertFalse(validator.is_valid(load(invalid)), contract)
        self.assertEqual(self.profile["profile_sha256"], digest({k: v for k, v in self.profile.items() if k != "profile_sha256"}))
        self.assertEqual(self.policy["policy_sha256"], digest({k: v for k, v in self.policy.items() if k != "policy_sha256"}))

    def test_oracle_meta_mutations_fail(self):
        cases = []
        profile = copy.deepcopy(self.schemas["tool_profile"]); profile["required"].remove("tool_id"); cases.append(("H2-02-META-REQUIRED", profile, "/required", self.oracle["contracts"]["ToolProfile"]["checks"][1]["expected"]))
        profile = copy.deepcopy(self.schemas["tool_profile"]); profile["additionalProperties"] = True; cases.append(("H2-02-META-CLOSED", profile, "/additionalProperties", False))
        profile = copy.deepcopy(self.schemas["tool_profile"]); profile["definitions"]["effect_class"]["enum"].append("shell"); cases.append(("H2-02-META-EFFECT", profile, "/definitions/effect_class/enum", self.oracle["contracts"]["ToolProfile"]["checks"][2]["expected"]))
        decision = copy.deepcopy(self.schemas["admission_decision"]); decision["properties"]["outcome"]["enum"].append("permit"); cases.append(("H2-02-META-OUTCOME", decision, "/properties/outcome/enum", self.oracle["contracts"]["AdmissionDecision"]["checks"][1]["expected"]))
        decision = copy.deepcopy(self.schemas["admission_decision"]); decision["properties"]["bindings"]["required"].remove("profile_sha256"); cases.append(("H2-02-META-HASH-BINDING", decision, "/properties/bindings/required", self.oracle["contracts"]["AdmissionDecision"]["checks"][2]["expected"]))
        for case_id, schema, path, expected in cases:
            with self.subTest(case_id=case_id): self.assertNotEqual(pointer(schema, path), expected)

    def test_matrix(self):
        executed = []
        def check(case_id, expected, mutate):
            intent, profiles, policy, context = self.base(); mutate(intent, profiles, policy, context)
            result = self.result(intent, profiles, policy, context)
            self.assertEqual(result["outcome"], "deny", case_id); self.assertEqual(result["stable_reason_code"], expected, case_id); executed.append(case_id)
        check("H2-02-NEG-UNKNOWN-TOOL", "unknown_tool", lambda i, p, b, c: i["tool_ref"].update(tool_id="unknown"))
        check("H2-02-NEG-UNKNOWN-PROFILE", "unknown_profile", lambda i, p, b, c: p.clear())
        check("H2-02-NEG-UNKNOWN-OPERATION", "unknown_operation", lambda i, p, b, c: i.update(operation_id="unknown"))
        check("H2-02-NEG-UNKNOWN-POLICY", "unknown_policy", lambda i, p, b, c: i["policy_context_ref"].update(policy_id="unknown"))
        def no_rule(i, p, b, c): b["rules"][0]["operation_id"] = "other"; self.bind(i, p, b, c)
        check("H2-02-NEG-UNKNOWN-POLICY-RULE", "unknown_policy_rule", no_rule)
        check("H2-02-NEG-PROFILE-HASH-MISMATCH", "profile_hash_mismatch", lambda i, p, b, c: i["tool_ref"].update(profile_sha256="c" * 64))
        check("H2-02-NEG-RUG-PULL", "profile_hash_mismatch", lambda i, p, b, c: p[0].update(provider_version="2.0"))
        check("H2-02-NEG-POLICY-HASH-MISMATCH", "policy_hash_mismatch", lambda i, p, b, c: b.update(policy_sha256="c" * 64))
        check("H2-02-NEG-VERSION", "invalid_intent", lambda i, p, b, c: i.update(intent_version="2.0"))
        check("H2-02-NEG-EXTRA-FIELD", "invalid_intent", lambda i, p, b, c: i.update(extensions={}))
        check("H2-02-NEG-ARG-EXTRA", "invalid_arguments", lambda i, p, b, c: i["arguments"].update(command="read"))
        check("H2-02-NEG-SECRET-FIELD", "sensitive_argument_rejected", lambda i, p, b, c: i["arguments"].update(api_key="not-a-secret"))
        check("H2-02-NEG-PATH-TRAVERSAL", "invalid_intent", lambda i, p, b, c: i["resource_scope"].update(path="../x"))
        check("H2-02-NEG-PATH-ABSOLUTE", "invalid_intent", lambda i, p, b, c: i["resource_scope"].update(path="/x"))
        check("H2-02-NEG-PATH-NUL", "invalid_intent", lambda i, p, b, c: i["resource_scope"].update(path="x\x00y"))
        check("H2-02-NEG-SCOPE-EMPTY", "invalid_intent", lambda i, p, b, c: i["resource_scope"].update(path=""))
        check("H2-02-NEG-SCOPE-OUTSIDE", "scope_not_allowlisted", lambda i, p, b, c: (i["resource_scope"].update(path="docs/other.md"), i["arguments"].update(path="docs/other.md")))
        check("H2-02-NEG-NETWORK-HOST", "invalid_intent", lambda i, p, b, c: i.update(resource_scope={"kind":"network","scheme":"ftp","hostname":"bad host","port":0}))
        check("H2-02-NEG-TOOL-CAPABILITY", "invalid_intent", lambda i, p, b, c: i.update(tool_capability={"write":True}))
        check("H2-02-NEG-MCP-ANNOTATION", "invalid_intent", lambda i, p, b, c: i.update(mcp_annotation={"destructive":False}))
        check("H2-02-NEG-SHELL-TEXT", "invalid_arguments", lambda i, p, b, c: i["arguments"].update(bash="cat x"))
        check("H2-02-NEG-SHELL-INDIRECT", "invalid_arguments", lambda i, p, b, c: i["arguments"].update(path="x;cat y"))
        check("H2-02-NEG-RUNTIME-ABSENT", "invalid_policy_context", lambda i, p, b, c: c.pop("runtime_capability"))
        check("H2-02-NEG-RUNTIME-UNDEMONSTRATED", "runtime_capability_not_demonstrated", lambda i, p, b, c: c["runtime_capability"].update(demonstrated=False))
        for effect in ("write", "network", "secrets", "destructive"):
            def sensitive(i, p, b, c, effect=effect): p[0]["operations"][0]["effect_classes"] = [effect]; self.bind(i, p, b, c)
            check(f"H2-02-NEG-EFFECT-{effect.upper()}", "effect_not_supported_in_h2_02", sensitive)
        def combined(i, p, b, c): p[0]["operations"][0]["effect_classes"] = ["read", "write"]; self.bind(i, p, b, c)
        check("H2-02-NEG-READ-COMBINED", "effect_not_supported_in_h2_02", combined)
        declared = 29
        self.assertEqual(len(executed), declared)
        print(f"matrix declared: {declared}\nmatrix executed: {len(executed)}\nmissing: 0\nskipped: 0\nfailed: 0")

    def test_determinism_redaction_and_no_execution_surface(self):
        intent, profiles, policy, context = self.base()
        first, second = self.result(intent, profiles, policy, context), self.result(intent, profiles, policy, context)
        self.assertEqual(first, second); self.assertEqual(first["outcome"], "admit_read"); self.assertEqual(first["stable_reason_code"], "admit_read")
        secret = copy.deepcopy(intent); secret["arguments"]["api_key"] = "never-serialize-this"
        result = self.result(secret, profiles, policy, context)
        self.assertNotIn("never-serialize-this", json.dumps(result))
        source = (ROOT / "tools/pdp.py").read_text()
        for forbidden in ("import subprocess", "import os", "os.system", "import socket", "urllib", "http.client", "mcp", "docker", "git.", "getenv", "environ", "shell"):
            self.assertNotIn(forbidden, source.lower())
        print("execution surfaces: subprocess=0 shell=0 socket=0 network=0 mcp=0 runtime=0")


if __name__ == "__main__": unittest.main(verbosity=2)
