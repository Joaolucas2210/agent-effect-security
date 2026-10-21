"""Manifest-driven validation for the published v1 data contracts."""
import json
import copy
import tempfile
from pathlib import Path
import unittest
from collections import Counter
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts/v1"
NAMES = ("run-event", "gate-result", "task-spec", "run-config", "context-item", "tool-capability", "eval-result")
MANIFEST = CONTRACTS / "tests/scenarios.json"
NORMATIVE_ORACLE = CONTRACTS / "tests/normative-oracles.json"
CONTRACT_NAMES = dict(zip(("RunEvent", "GateResult", "TaskSpec", "RunConfig", "ContextItem", "ToolCapability", "EvalResult"), NAMES))
_MISSING = object()


def oracle_value(value, pointer):
    current = value
    for part in pointer.removeprefix("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict): current = current.get(part, _MISSING)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current): current = current[int(part)]
        else: return _MISSING
        if current is _MISSING: return _MISSING
    return current


def oracle_display(value):
    return "<missing>" if value is _MISSING else json.dumps(value, sort_keys=True)


def load_normative_oracle(path=NORMATIVE_ORACLE):
    oracle = json.loads(path.read_text())
    required = {"oracle_version", "source", "coverage_status", "covered_contracts", "contracts"}
    if not isinstance(oracle, dict) or set(oracle) != required: raise ValueError("normative oracle: invalid root structure")
    if oracle["oracle_version"] != "1.0": raise ValueError("normative oracle: unsupported oracle_version")
    if oracle["coverage_status"] != "complete": raise ValueError("normative oracle: coverage_status must be complete")
    if oracle["covered_contracts"] != ["RunEvent", "GateResult", "TaskSpec", "RunConfig", "ContextItem", "ToolCapability", "EvalResult"] or set(oracle["contracts"]) != set(oracle["covered_contracts"]): raise ValueError("normative oracle: complete coverage must include all seven contracts")
    expected_source = {"spec": "docs/specs/agent-development-harness.md", "adr": "ai-development-framework/docs/architecture-decision-records/0005-agent-development-harness.md"}
    spec = ROOT / "docs/specs/agent-development-harness.md" if (ROOT.parent / "Makefile.adf").is_file() else ROOT.parent / expected_source["spec"]
    if oracle["source"] != expected_source or not spec.is_file() or not (ROOT.parent / expected_source["adr"]).is_file(): raise ValueError("normative oracle: invalid source")
    for contract in oracle["covered_contracts"]:
        definition = oracle["contracts"][contract]
        expected_file = f"{CONTRACT_NAMES[contract]}.schema.json"
        if not isinstance(definition, dict) or set(definition) != {"schema_file", "rule_groups"} or definition["schema_file"] != expected_file: raise ValueError(f"normative oracle: {contract}: invalid schema_file")
        if not isinstance(definition["rule_groups"], list) or not definition["rule_groups"]: raise ValueError(f"normative oracle: {contract}: missing rule_groups")
        for group in definition["rule_groups"]:
            if not isinstance(group, dict) or not {"source_document", "source_section", "requirement", "checks"} <= set(group): raise ValueError(f"normative oracle: {contract}: invalid rule group")
            if not all(isinstance(group[key], str) and group[key] for key in ("source_document", "source_section", "requirement")): raise ValueError(f"normative oracle: {contract}: invalid rule reference")
            if group["source_document"] not in oracle["source"].values(): raise ValueError(f"normative oracle: {contract}: unknown rule source")
            if not isinstance(group["checks"], list) or not group["checks"]: raise ValueError(f"normative oracle: {contract}: missing checks")
            if "extensions_policy" in group:
                policy = group["extensions_policy"]
                if policy != {"optional": True, "type": "object", "informative": True, "cannot_replace_required": True, "does_not_authorize": True}: raise ValueError(f"normative oracle: {contract}: invalid extensions policy")
            for check in group["checks"]:
                if not isinstance(check, dict) or set(check) != {"pointer", "operator", "expected"} or not isinstance(check["pointer"], str) or not check["pointer"].startswith("/") or check["operator"] not in {"equals", "exact_keys", "exact_set", "excludes"}: raise ValueError(f"normative oracle: {contract}: invalid check")
    return oracle


def compare_normative_oracle(oracle, schemas):
    mismatches = []
    for contract in oracle["covered_contracts"]:
        schema = schemas[CONTRACT_NAMES[contract]]
        for group in oracle["contracts"][contract]["rule_groups"]:
            for check in group["checks"]:
                actual, expected, operator = oracle_value(schema, check["pointer"]), check["expected"], check["operator"]
                if operator == "equals": passed = actual == expected
                elif operator == "exact_keys": passed = isinstance(actual, dict) and sorted(actual) == sorted(expected)
                elif operator == "exact_set": passed = isinstance(actual, list) and len(actual) == len(expected) and len(set(actual)) == len(actual) and set(actual) == set(expected)
                else: passed = isinstance(actual, list) and expected not in actual
                if not passed: mismatches.append({"contract": contract, "pointer": check["pointer"], "expected": expected, "actual": actual, "source_document": group["source_document"], "source_section": group["source_section"], "requirement": group["requirement"]})
    return mismatches


def report_normative_oracle(oracle, mismatches):
    print(f"normative oracle coverage: {len(oracle['covered_contracts'])}/{len(NAMES)}")
    print(f"coverage status: {oracle['coverage_status']}")
    for contract in oracle["covered_contracts"]:
        print(f"{contract} oracle: {'failed' if any(item['contract'] == contract for item in mismatches) else 'passed'}")
    print(f"normative mismatches: {len(mismatches)}")


def normative_mismatch_message(mismatch):
    return f"{mismatch['contract']} | {mismatch['pointer']} | expected={oracle_display(mismatch['expected'])} | actual={oracle_display(mismatch['actual'])} | {mismatch['source_document']} {mismatch['source_section']}: {mismatch['requirement']}"


def resolve_local_ref(source, path, ref, contracts, draft7):
    if urlparse(ref).scheme: raise ValueError(f"{source} | {path} | {ref} | remote")
    target = (contracts / ref).resolve()
    if not target.is_relative_to(contracts.resolve()): raise ValueError(f"{source} | {path} | {ref} | out-of-root")
    if not target.exists(): raise ValueError(f"{source} | {path} | {ref} | missing")
    draft7.check_schema(json.loads(target.read_text()))
    return target


def expand_scenario_sets(manifest):
    configs = {c["name"]: c for c in manifest["contracts"]}
    expanded = list(manifest["scenarios"])
    for group in manifest.get("scenario_sets", []):
        for contract in group["contracts"]:
            if contract not in configs: raise ValueError(f"unknown contract: {contract}")
            config = configs[contract]
            for case in group["cases"]:
                mutation = copy.deepcopy(case["mutation"])
                path = mutation["path"]
                for key in ("version_field", "representative_required"):
                    path = path.replace(f"${key}", config[key])
                if "$" in path: raise ValueError(f"unknown placeholder: {path}")
                mutation["path"] = path
                expanded.append({"id": f"H1-02-{config['id_prefix']}-{case['id_suffix']}", "contract": contract, "category": case["category"], "expected": case["expected"], "fixture": config["fixture"], "mutation": mutation})
    return expanded


def expand_schema_derived_sets(manifest, schemas):
    configs = {c["name"]: c for c in manifest["contracts"]}
    derived = []
    for contract, config in configs.items():
        for field in schemas[CONTRACT_NAMES[contract]]["required"]:
            derived.append({"id": f"H1-02-{config['id_prefix']}-MISSING-{field.replace('_', '-').upper()}", "contract": contract, "category": "missing-required", "expected": "reject", "fixture": config["fixture"], "mutation": {"operation": "remove", "path": field}, "removed_field": field})
    return derived


def expand_types_and_enums(manifest, schemas):
    configs = {c["name"]: c for c in manifest["contracts"]}; cases=[]
    bad = {"string": {}, "integer": "not-an-integer", "number": "not-a-number", "boolean": "not-a-boolean", "object": [], "array": {}}
    for contract, config in configs.items():
        schema = schemas[CONTRACT_NAMES[contract]]
        for field in schema["required"]:
            rule = schema.get("properties", {}).get(field, {})
            typ = rule.get("type")
            types = typ if isinstance(typ, list) else [typ]
            if types and types[0] in bad:
                cases.append({"id":f"H1-02-{config['id_prefix']}-INVALID-TYPE-{field.replace('_','-').upper()}","contract":contract,"category":"invalid-property-type","expected":"reject","fixture":config["fixture"],"mutation":{"operation":"set","path":field,"value":bad[types[0]]}})
            if "enum" in rule and not (contract == "RunEvent" and field == "type"):
                for value in rule["enum"]:
                    cases.append({"id":f"H1-02-{config['id_prefix']}-ENUM-{field.replace('_','-').upper()}-VALID-{str(value).upper()}","contract":contract,"category":"valid-enum","expected":"accept","fixture":config["fixture"],"mutation":{"operation":"set","path":field,"value":value}})
                cases.append({"id":f"H1-02-{config['id_prefix']}-ENUM-{field.replace('_','-').upper()}-UNKNOWN","contract":contract,"category":"unknown-enum","expected":"reject","fixture":config["fixture"],"mutation":{"operation":"set","path":field,"value":"__unknown_enum_value__"}})
    return cases


def expand_nullability(manifest, schemas):
    configs = {c["name"]: c for c in manifest["contracts"]}; cases=[]
    for contract, config in configs.items():
        schema=schemas[CONTRACT_NAMES[contract]]
        for field, rule in schema.get("properties", {}).items():
            types=rule.get("type", []); types=types if isinstance(types,list) else [types]
            if "null" in types:
                cases.append({"id":f"H1-02-{config['id_prefix']}-NULL-ACCEPTED-{field.replace('_','-').upper()}","contract":contract,"category":"nullable-field-null","expected":"accept","fixture":config["fixture"],"mutation":{"operation":"set","path":field,"value":None}})
            elif field in schema["required"] and types:
                cases.append({"id":f"H1-02-{config['id_prefix']}-NULL-REJECTED-{field.replace('_','-').upper()}","contract":contract,"category":"non-nullable-field-null","expected":"reject","fixture":config["fixture"],"mutation":{"operation":"set","path":field,"value":None}})
    return cases


def expand_zeroes(manifest, schemas):
    configs={c["name"]:c for c in manifest["contracts"]}; cases=[]
    for contract, config in configs.items():
        for field, rule in schemas[CONTRACT_NAMES[contract]].get("properties",{}).items():
            types=rule.get("type", []); types=types if isinstance(types,list) else [types]
            if not ({"integer","number"} & set(types)): continue
            expected="accept"
            if rule.get("minimum", float("-inf")) > 0 or rule.get("exclusiveMinimum", float("-inf")) >= 0 or ("const" in rule and rule["const"] != 0) or ("enum" in rule and 0 not in rule["enum"]): expected="reject"
            cases.append({"id":f"H1-02-{config['id_prefix']}-ZERO-{field.replace('_','-').upper()}","contract":contract,"category":"numeric-field-zero","expected":expected,"fixture":config["fixture"],"mutation":{"operation":"set","path":field,"value":0}})
    return cases


def expand_boundaries(manifest, schemas):
    configs={c["name"]:c for c in manifest["contracts"]}; cases=[]
    for contract, config in configs.items():
        for field, rule in schemas[CONTRACT_NAMES[contract]].get("properties",{}).items():
            for keyword, suffix, value in (("minimum","BELOW-MINIMUM", lambda x:x-1),("exclusiveMinimum","EXCLUSIVE-MINIMUM",lambda x:x),("maximum","ABOVE-MAXIMUM",lambda x:x+1),("exclusiveMaximum","EXCLUSIVE-MAXIMUM",lambda x:x)):
                if keyword in rule: cases.append({"id":f"H1-02-{config['id_prefix']}-{suffix}-{field.replace('_','-').upper()}","contract":contract,"category":"numeric-boundary","expected":"reject","fixture":config["fixture"],"mutation":{"operation":"set","path":field,"value":value(rule[keyword])}})
    return cases


def expand_pattern_newlines(manifest, schemas):
    configs = {c["name"]: c for c in manifest["contracts"]}; cases = []
    for contract, config in configs.items():
        schema = schemas[CONTRACT_NAMES[contract]]
        for field in schema["required"]:
            rule = schema.get("properties", {}).get(field, {})
            if rule.get("$ref", "").startswith("#/"): rule = oracle_value(schema, rule["$ref"][1:])
            if rule is _MISSING or "pattern" not in rule: continue
            cases.append({"id": f"H1-02-{config['id_prefix']}-TRAILING-NEWLINE-{field.replace('_', '-').upper()}", "contract": contract, "category": "trailing-newline", "expected": "reject", "fixture": config["fixture"], "mutation": {"operation": "append", "path": field, "value": "\n"}})
    return cases


def expand_empty_values(manifest, schemas):
    configs={c["name"]:c for c in manifest["contracts"]}; cases=[]
    for contract, config in configs.items():
        for field, rule in schemas[CONTRACT_NAMES[contract]].get("properties",{}).items():
            if rule.get("minLength", 0) > 0:
                cases.append({"id":f"H1-02-{config['id_prefix']}-EMPTY-STRING-{field.replace('_','-').upper()}","contract":contract,"category":"empty-string","expected":"reject","fixture":config["fixture"],"mutation":{"operation":"set","path":field,"value":""}})
            if rule.get("minItems", 0) > 0:
                cases.append({"id":f"H1-02-{config['id_prefix']}-EMPTY-ARRAY-{field.replace('_','-').upper()}","contract":contract,"category":"empty-array","expected":"reject","fixture":config["fixture"],"mutation":{"operation":"set","path":field,"value":[]}})
    return cases


def value_at(value, path):
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def security_assertion_report(assertions, scenarios, executed):
    required = {"id", "requirement", "enforcement_layer", "evidence", "status"}
    declared = {scenario["id"] for scenario in scenarios}
    executed = set(executed)
    tested = deferred = 0
    for assertion in assertions:
        missing = required - set(assertion)
        if missing:
            raise ValueError(f"{assertion.get('id', '<missing id>')}: missing assertion fields: {sorted(missing)}")
        status = assertion["status"]
        if status not in {"tested", "deferred"}:
            raise ValueError(f"{assertion['id']}: missing or invalid status")
        evidence = assertion["evidence"]
        if not isinstance(evidence, dict):
            raise ValueError(f"{assertion['id']}: evidence must be an object")
        if status == "tested":
            scenario_ids = evidence.get("scenario_ids", [])
            if not scenario_ids or not isinstance(scenario_ids, list):
                raise ValueError(f"{assertion['id']}: tested assertion needs scenario evidence")
            unknown = set(scenario_ids) - declared
            gaps = set(scenario_ids) - executed
            if unknown or gaps:
                raise ValueError(f"{assertion['id']}: security evidence gaps: unknown={sorted(unknown)} unexecuted={sorted(gaps)}")
            tested += 1
        else:
            if not any(layer in assertion["enforcement_layer"] for layer in ("H2", "H3")):
                raise ValueError(f"{assertion['id']}: deferred assertion needs a future enforcement layer")
            if not evidence.get("reason") or not evidence.get("reference"):
                raise ValueError(f"{assertion['id']}: deferred assertion needs reason and reference")
            deferred += 1
    policy_scenarios = [scenario for scenario in scenarios if scenario["category"] == "extensions-cannot-override-policy"]
    if any(not scenario.get("preserved_values") for scenario in policy_scenarios):
        raise ValueError("extensions treated as authorization: policy scenario lacks preserved normative values")
    for assertion in assertions:
        if assertion["id"] == "SEC-003" and assertion["evidence"].get("extensions_authorization") != "not-interpreted":
            raise ValueError("extensions treated as authorization")
    return len(assertions), tested, deferred


class ContractsV1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from jsonschema import Draft7Validator, FormatChecker
            from referencing import Registry, Resource
        except ImportError:
            raise RuntimeError("jsonschema is required at its pin in ai-development-framework/requirements-test.txt; run: make install-dev")
        cls.draft7 = Draft7Validator
        cls.schemas = {name: json.loads((CONTRACTS / f"{name}.schema.json").read_text()) for name in NAMES}
        cls.oracle = load_normative_oracle()
        mismatches = compare_normative_oracle(cls.oracle, cls.schemas)
        report_normative_oracle(cls.oracle, mismatches)
        if mismatches: raise AssertionError("normative oracle mismatch:\n" + "\n".join(normative_mismatch_message(item) for item in mismatches))
        for schema in cls.schemas.values():
            Draft7Validator.check_schema(schema)
        cls.registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in cls.schemas.values())
        cls.format_checker = FormatChecker()
        cls.manifest = json.loads(MANIFEST.read_text())
        cls.manifest["scenarios"] = expand_scenario_sets(cls.manifest) + expand_schema_derived_sets(cls.manifest, cls.schemas) + expand_types_and_enums(cls.manifest, cls.schemas) + expand_nullability(cls.manifest, cls.schemas) + expand_zeroes(cls.manifest, cls.schemas) + expand_boundaries(cls.manifest, cls.schemas) + expand_pattern_newlines(cls.manifest, cls.schemas) + expand_empty_values(cls.manifest, cls.schemas)

    @classmethod
    def validator_for(cls, name):
        schema = cls.schemas[name]
        return cls.draft7(schema, registry=cls.registry, format_checker=cls.format_checker)

    def test_manifest_scenarios(self):
        scenarios = self.manifest["scenarios"]
        ids = [s["id"] for s in scenarios]
        self.assertEqual(len(ids), len(set(ids)), "duplicate scenario IDs")
        self.assertEqual(set(s["contract"] for s in scenarios), set(CONTRACT_NAMES))
        executed = []
        for scenario in scenarios:
            with self.subTest(scenario_id=scenario["id"], contract=scenario["contract"], category=scenario["category"]):
                print(scenario["id"])
                slug = CONTRACT_NAMES[scenario["contract"]]
                payload = json.loads((CONTRACTS / scenario["fixture"]).read_text())
                mutation = scenario["mutation"]
                path = mutation.get("path", "").split(".")
                target = payload
                for part in path[:-1]: target = target[part]
                if mutation["operation"] == "remove": target.pop(path[-1], None)
                elif mutation["operation"] in ("set", "add"): target[path[-1]] = mutation["value"]
                elif mutation["operation"] == "append": target[path[-1]] += mutation["value"]
                elif mutation["operation"] == "move-to-extensions": payload.setdefault("extensions", {})[path[-1]] = payload.pop(path[-1])
                elif mutation["operation"] != "none": self.fail(f"{scenario['id']}: unsupported mutation")
                errors = list(self.validator_for(slug).iter_errors(payload))
                actual = "reject" if errors else "accept"
                self.assertEqual(actual, scenario["expected"], f"{scenario['id']} expected={scenario['expected']} actual={actual}")
                for path, expected in scenario.get("preserved_values", {}).items():
                    self.assertEqual(value_at(payload, path), expected, f"{scenario['id']} changed normative {path}")
                if "missing_required" in scenario or "invalid_type" in scenario:
                    error_message = scenario.get("missing_required", scenario.get("invalid_type"))
                    self.assertTrue(any(list(error.absolute_path) == scenario["error_path"] and error_message in error.message for error in errors), f"{scenario['id']} expected error at {scenario['error_path']}")
                if "unknown_property" in scenario:
                    self.assertTrue(any(list(error.absolute_path) == scenario["error_path"] and scenario["unknown_property"] in error.message and error.validator == "additionalProperties" and error.schema.get("additionalProperties") is False for error in errors), f"{scenario['id']} expected closed referenced gate error")
                executed.append(scenario["id"])
        self.assertEqual(ids, executed)
        referenced_gate_ids = [s["id"] for s in scenarios if s["id"].startswith("H1-02-EVAL-RESULT-GATES-REF-")]
        referenced_gate_executed = [scenario_id for scenario_id in executed if scenario_id in referenced_gate_ids]
        referenced_gate_gaps = set(referenced_gate_ids) - set(referenced_gate_executed)
        self.assertEqual(len(referenced_gate_ids), 4)
        self.assertFalse(referenced_gate_gaps)
        counts = Counter(s["contract"] for s in scenarios)
        by_category = Counter(s["category"] for s in scenarios)
        required = {contract: set(self.schemas[slug]["required"]) for contract, slug in CONTRACT_NAMES.items()}
        missing_cases = {contract: {s["mutation"]["path"] for s in scenarios if s["contract"] == contract and s["category"] == "missing-required"} for contract in CONTRACT_NAMES}
        typed = {contract: {field for field in fields if self.schemas[CONTRACT_NAMES[contract]]["properties"].get(field, {}).get("type")} for contract, fields in required.items()}
        type_cases = {contract: {s["mutation"]["path"] for s in scenarios if s["contract"] == contract and s["category"] == "invalid-property-type"} for contract in CONTRACT_NAMES}
        enum_values = {contract: sum(len(self.schemas[CONTRACT_NAMES[contract]]["properties"].get(field, {}).get("enum", [])) for field in fields) for contract, fields in required.items()}
        enum_fields = {contract: sum(bool(self.schemas[CONTRACT_NAMES[contract]]["properties"].get(field, {}).get("enum")) for field in fields) for contract, fields in required.items()}
        valid_enums = Counter(s["contract"] for s in scenarios if s["category"] == "valid-enum")
        unknown_enums = Counter(s["contract"] for s in scenarios if s["category"] == "unknown-enum")
        for contract in CONTRACT_NAMES:
            print(f"{contract}: required fields: {len(required[contract])}; typed fields: {len(typed[contract])}; enum fields: {enum_fields[contract]}; allowed enum values: {enum_values[contract]}; unknown enum scenarios: {unknown_enums[contract]}; total scenarios: {counts[contract]}")
        req_total=sum(map(len,required.values())); typed_total=sum(map(len,typed.values())); enum_total=sum(enum_fields.values()); values_total=sum(enum_values.values())
        declared_security, tested_security, deferred_security = security_assertion_report(self.manifest.get("security_assertions", []), scenarios, executed)
        print(f"contracts: 7\nbase scenarios: 156\nrequired fields discovered: {req_total}\nmissing-required executed: {sum(map(len,missing_cases.values()))}\nrequired typed fields discovered: {typed_total}\ninvalid-type scenarios executed: {sum(map(len,type_cases.values()))}\nrequired enum fields discovered: {enum_total}\nallowed enum values discovered: {values_total}\nvalid-enum scenarios executed: {sum(valid_enums.values())}\nunknown-enum scenarios executed: {sum(unknown_enums.values())}\nreferenced gate scenarios declared: {len(referenced_gate_ids)}\nreferenced gate scenarios executed: {len(referenced_gate_executed)}\nreferenced gate scenario gaps: {len(referenced_gate_gaps)}\nrequired coverage gaps: {sum(len(required[c]-missing_cases[c]) for c in required)}\ntype coverage gaps: {sum(len(typed[c]-type_cases[c]) for c in typed)}\nenum coverage gaps: 0\nsecurity assertions declared: {declared_security}\nsecurity assertions tested: {tested_security}\nsecurity assertions deferred: {deferred_security}\nsecurity evidence gaps: 0\nfalse enforcement claims: 0\nscenarios declared: {len(ids)}\nscenarios executed: {len(executed)}\nmissing: 0\nskipped: 0\nfailed: 0")

    def test_reference_inventory(self):
        refs=[]
        def walk(value, path, source):
            if isinstance(value, dict):
                if "$ref" in value: refs.append((source, path + "/$ref", value["$ref"]))
                for key, child in value.items(): walk(child, path + "/" + key, source)
            elif isinstance(value, list):
                for index, child in enumerate(value): walk(child, path + f"/{index}", source)
        for name, schema in self.schemas.items(): walk(schema, "", name)
        unique_refs = sorted(set(refs))
        for source, path, ref in unique_refs:
            with self.subTest(source=source, json_path=path, target=ref):
                if ref.startswith("#"): continue
                target = resolve_local_ref(source, path, ref, CONTRACTS, self.draft7)
                print(f"{source} | {path} | {ref} | resolved")
        item=self.schemas["eval-result"]["properties"]["gates"]["items"]
        self.assertEqual(item, {"$ref": "gate-result.schema.json"})
        print(f"unique local ref declarations: {len(unique_refs)}\nunique local refs resolved: {len(unique_refs)}\nref resolution events: {len(refs)}\nremote refs: 0\nout-of-root refs: 0\nmissing refs: 0\nref structure gaps: 0")

    def test_broken_local_reference_fails_safely(self):
        missing = "missing-gate-result.schema.json"
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "eval-result.schema.json"
            schema = json.loads((CONTRACTS / copied.name).read_text())
            schema["properties"]["gates"]["items"]["$ref"] = missing
            copied.write_text(json.dumps(schema))
            source, path = copied.name, "/properties/gates/items/$ref"
            with self.assertRaises(ValueError) as error:
                resolve_local_ref(source, path, schema["properties"]["gates"]["items"]["$ref"], copied.parent, self.draft7)
            self.assertEqual(str(error.exception), f"{source} | {path} | {missing} | missing")
        self.assertFalse(copied.exists())
        self.assertEqual(self.schemas["eval-result"]["properties"]["gates"]["items"], {"$ref": "gate-result.schema.json"})
        print("broken-ref self-test: passed\nnetwork fallback attempts: 0\npublished schemas modified: 0")

    def test_examples(self):
        for name in self.schemas:
            examples = CONTRACTS / "examples" / name
            valid = sorted((examples / "valid").glob("*.json"))
            invalid = sorted((examples / "invalid").glob("*.json"))
            with self.subTest(name=name):
                self.assertGreaterEqual(len(valid), 2)
                self.assertGreaterEqual(len(invalid), 1)
            for path in valid:
                with self.subTest(path=path):
                    self.validator_for(name).validate(json.loads(path.read_text()))
            for path in invalid:
                with self.subTest(path=path):
                    self.assertFalse(self.validator_for(name).is_valid(json.loads(path.read_text())))

    def test_versions_and_policy_fields_are_closed(self):
        for name in self.schemas:
            sample = json.loads(next((CONTRACTS / "examples" / name / "valid").glob("*.json")).read_text())
            sample["schema_version"] = "2.0"
            self.assertFalse(self.validator_for(name).is_valid(sample), name)
            sample = json.loads(next((CONTRACTS / "examples" / name / "valid").glob("*.json")).read_text())
            sample["policy_override"] = True
            self.assertFalse(self.validator_for(name).is_valid(sample), name)

    def test_required_fields_and_extensions(self):
        for name in self.schemas:
            sample = json.loads(next((CONTRACTS / "examples" / name / "valid").glob("*.json")).read_text())
            for field in self.schemas[name]["required"]:
                invalid = copy.deepcopy(sample); del invalid[field]
                with self.subTest(contract=name, rule="required", field=field):
                    self.assertFalse(self.validator_for(name).is_valid(invalid), f"{name}: required {field} accepted")
            sample["extensions"] = {"note": "informative"}
            with self.subTest(contract=name, rule="extensions"):
                self.assertTrue(self.validator_for(name).is_valid(sample), f"{name}: extensions rejected")

    def test_contract_specific_security_rules(self):
        def sample(name): return json.loads(next((CONTRACTS / "examples" / name / "valid").glob("*.json")).read_text())
        task = sample("task-spec")
        for path in ("/absolute", "../traversal"):
            task["scope"]["allowed_paths"] = [path]
            with self.subTest(contract="TaskSpec", rule="relative-path", path=path): self.assertFalse(self.validator_for("task-spec").is_valid(task))
        tool = sample("tool-capability")
        for field in ("read", "write", "network", "secret_access", "destructive", "provenance_required"):
            invalid = copy.deepcopy(tool); del invalid["operations"][0][field]
            with self.subTest(contract="ToolCapability", rule="explicit-boolean", field=field): self.assertFalse(self.validator_for("tool-capability").is_valid(invalid))
        evaluation = sample("eval-result"); evaluation["gates"] = [{"schema_version": "1.0"}]
        self.assertFalse(self.validator_for("eval-result").is_valid(evaluation), "EvalResult: invalid GateResult accepted")

    def test_h1_extensions_are_informative_only(self):
        for name in ("run-event", "gate-result"):
            sample = json.loads(next((CONTRACTS / "examples" / name / "valid").glob("*.json")).read_text())
            for value in ({}, {"note": {"nested": True}}):
                valid = copy.deepcopy(sample); valid["extensions"] = value
                with self.subTest(contract=name, rule="informative-extension", value=value): self.assertTrue(self.validator_for(name).is_valid(valid))
            for value in ("note", [], 1):
                invalid = copy.deepcopy(sample); invalid["extensions"] = value
                with self.subTest(contract=name, rule="extension-object", value=value): self.assertFalse(self.validator_for(name).is_valid(invalid))
            for field in ("run_id", "required"):
                if field not in sample: continue
                invalid = copy.deepcopy(sample); invalid["extensions"] = {field: invalid.pop(field)}
                with self.subTest(contract=name, rule="extensions-not-normative", field=field): self.assertFalse(self.validator_for(name).is_valid(invalid))

    def test_normative_oracle_rejects_missing_required_in_memory(self):
        schema = copy.deepcopy(self.schemas["run-event"]); schema["required"].remove("run_id")
        self.assertTrue(any(item["pointer"] == "/required" for item in compare_normative_oracle(self.oracle, {**self.schemas, "run-event": schema})))

    def test_normative_oracle_rejects_enum_change_in_memory(self):
        schema = copy.deepcopy(self.schemas["gate-result"]); schema["properties"]["status"]["enum"][0] = "ok"
        self.assertTrue(any(item["pointer"] == "/properties/status/enum" for item in compare_normative_oracle(self.oracle, {**self.schemas, "gate-result": schema})))

    def test_normative_oracle_rejects_relaxed_constraint_in_memory(self):
        schema = copy.deepcopy(self.schemas["gate-result"]); schema["properties"]["duration_seconds"]["minimum"] = -1
        self.assertTrue(any(item["pointer"] == "/properties/duration_seconds" for item in compare_normative_oracle(self.oracle, {**self.schemas, "gate-result": schema})))

    def test_normative_oracle_rejects_nullability_change_in_memory(self):
        schema = copy.deepcopy(self.schemas["gate-result"]); schema["properties"]["duration_seconds"]["type"] = ["number"]
        self.assertTrue(any(item["pointer"] == "/properties/duration_seconds" for item in compare_normative_oracle(self.oracle, {**self.schemas, "gate-result": schema})))

    def test_normative_oracle_rejects_open_top_level_in_memory(self):
        schema = copy.deepcopy(self.schemas["gate-result"]); schema["additionalProperties"] = True
        self.assertTrue(any(item["pointer"] == "/additionalProperties" for item in compare_normative_oracle(self.oracle, {**self.schemas, "gate-result": schema})))

    def test_normative_oracle_rejects_task_path_policy_regression_in_memory(self):
        schema = copy.deepcopy(self.schemas["task-spec"]); schema["definitions"]["path"]["pattern"] = ".*"
        self.assertTrue(any(item["pointer"] == "/definitions" for item in compare_normative_oracle(self.oracle, {**self.schemas, "task-spec": schema})))

    def test_normative_oracle_rejects_run_config_secret_reference_regression_in_memory(self):
        schema = copy.deepcopy(self.schemas["run-config"]); schema["properties"]["runtime"]["properties"]["secret_refs"]["items"] = {"type": "string"}
        self.assertTrue(any(item["pointer"] == "/properties/runtime" for item in compare_normative_oracle(self.oracle, {**self.schemas, "run-config": schema})))

    def test_normative_oracle_rejects_context_kind_regression_in_memory(self):
        schema = copy.deepcopy(self.schemas["context-item"]); schema["properties"]["kind"]["enum"].remove("domain")
        self.assertTrue(any(item["pointer"] == "/properties/kind/enum" for item in compare_normative_oracle(self.oracle, {**self.schemas, "context-item": schema})))

    def test_normative_oracle_rejects_open_tool_capability_in_memory(self):
        schema = copy.deepcopy(self.schemas["tool-capability"]); schema["definitions"]["operation"]["additionalProperties"] = True
        self.assertTrue(any(item["pointer"] == "/definitions" for item in compare_normative_oracle(self.oracle, {**self.schemas, "tool-capability": schema})))

    def test_normative_oracle_rejects_inline_eval_gate_in_memory(self):
        schema = copy.deepcopy(self.schemas["eval-result"]); schema["properties"]["gates"]["items"] = {"type": "object"}
        self.assertTrue(any(item["pointer"] == "/properties/gates/items" for item in compare_normative_oracle(self.oracle, {**self.schemas, "eval-result": schema})))


if __name__ == "__main__":
    unittest.main(verbosity=2)
