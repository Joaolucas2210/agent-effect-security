import copy
import json
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft7Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "modes"))
from resolver import resolve  # noqa: E402


class ModeResolutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = ROOT / "contracts/v1"
        modes = ROOT / "modes/v1"
        cls.schemas = {
            "catalog": json.loads((modes / "mode-catalog.schema.json").read_text()),
            "request": json.loads((modes / "resolution-request.schema.json").read_text()),
            "resolved": json.loads((modes / "resolved-run-config.schema.json").read_text()),
            "task": json.loads((contracts / "task-spec.schema.json").read_text()),
            "run_config": json.loads((contracts / "run-config.schema.json").read_text()),
        }
        for schema in cls.schemas.values():
            Draft7Validator.check_schema(schema)
        cls.registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in cls.schemas.values()
        )
        cls.catalog = json.loads((modes / "mode-catalog.json").read_text())
        cls.request = json.loads((modes / "examples/valid/resolution-request.json").read_text())
        cls.unknown_request = json.loads((modes / "examples/invalid/unknown-mode.json").read_text())

    def resolve(self, request=None, catalog=None):
        return resolve(request or copy.deepcopy(self.request), catalog or copy.deepcopy(self.catalog), self.schemas)

    def assert_error(self, result, code):
        self.assertEqual(result["errors"][0]["code"], code)
        self.assertNotIn("run_config", result)

    def test_all_approved_modes_resolve_to_valid_run_config(self):
        for mode in ("prototyper", "builder", "grower", "sweeper", "maintainer"):
            request = copy.deepcopy(self.request)
            request["requested_mode"] = mode
            result = self.resolve(request)
            with self.subTest(mode=mode):
                self.assertEqual(result["mode_id"], mode)
                self.assertEqual(result["run_config"]["mode"]["id"], mode)
                Draft7Validator(self.schemas["run_config"], registry=self.registry).validate(result["run_config"])
                Draft7Validator(self.schemas["resolved"], registry=self.registry).validate(result)

    def test_catalog_accepts_exactly_the_five_approved_modes(self):
        self.assertIn("run_config", self.resolve())
        unapproved = copy.deepcopy(self.catalog)
        unapproved["modes"][0]["id"] = "unapproved"
        self.assert_error(self.resolve(catalog=unapproved), "invalid_catalog")
        incomplete = copy.deepcopy(self.catalog)
        incomplete["modes"].pop()
        self.assert_error(self.resolve(catalog=incomplete), "invalid_catalog")
        extra = copy.deepcopy(self.catalog)
        extra["modes"].append(copy.deepcopy(extra["modes"][0]))
        extra["modes"][-1]["id"] = "unapproved"
        self.assert_error(self.resolve(catalog=extra), "invalid_catalog")
        duplicate = copy.deepcopy(self.catalog)
        duplicate["modes"][-1]["id"] = duplicate["modes"][0]["id"]
        self.assert_error(self.resolve(catalog=duplicate), "invalid_catalog")

    def test_missing_and_unknown_modes_fail_closed(self):
        missing = copy.deepcopy(self.request)
        del missing["requested_mode"]
        self.assert_error(self.resolve(missing), "invalid_request")
        self.assert_error(self.resolve(self.unknown_request), "unknown_mode")

    def test_invalid_and_incomplete_requests_fail_closed(self):
        unknown = copy.deepcopy(self.request)
        unknown["unknown"] = True
        self.assert_error(self.resolve(unknown), "invalid_request")
        incomplete = copy.deepcopy(self.request)
        del incomplete["execution_context"]["adapter"]
        self.assert_error(self.resolve(incomplete), "invalid_request")
        missing_hash = copy.deepcopy(self.request)
        del missing_hash["execution_context"]["task_ref_sha256"]
        self.assert_error(self.resolve(missing_hash), "invalid_request")

    def test_allowlisted_overrides_apply_and_budget_only_reduces(self):
        request = copy.deepcopy(self.request)
        request["requested_overrides"] = {
            "model": {"parameters": {"temperature": 0}},
            "seed": 0,
            "experiment_id": "experiment-1",
            "trial_id": "trial-1",
            "budget": {"tokens": 40, "seconds": 30, "tool_calls": 4},
        }
        result = self.resolve(request)
        self.assertEqual(result["run_config"]["model"]["parameters"], {"temperature": 0})
        self.assertEqual(result["run_config"]["budget"]["tokens"], 40)
        self.assertEqual(result["provenance"]["budget.tokens"]["source"], "explicit_request")
        expanded = copy.deepcopy(request)
        expanded["requested_overrides"]["budget"]["tokens"] = 51
        self.assert_error(self.resolve(expanded), "budget_expansion")

    def test_prohibited_overrides_and_constraints_fail_closed(self):
        runtime = copy.deepcopy(self.request)
        runtime["requested_overrides"] = {"runtime": {}}
        self.assert_error(self.resolve(runtime), "override_prohibited")
        adapter = copy.deepcopy(self.request)
        adapter["requested_overrides"] = {"adapter": {}}
        self.assert_error(self.resolve(adapter), "override_prohibited")
        hashes = copy.deepcopy(self.request)
        hashes["requested_overrides"] = {"policy_hash": "e" * 64}
        self.assert_error(self.resolve(hashes), "override_prohibited")
        blocked = copy.deepcopy(self.request)
        blocked["requested_overrides"] = {"seed": 0}
        blocked["execution_context"]["organizational_constraints"]["prohibited_override_paths"] = ["seed"]
        self.assert_error(self.resolve(blocked), "constraint_conflict")
        mode_conflict = copy.deepcopy(self.request)
        mode_conflict["requested_mode"] = "maintainer"
        mode_conflict["execution_context"]["organizational_constraints"]["allowed_modes"] = ["builder"]
        self.assert_error(self.resolve(mode_conflict), "constraint_conflict")
        ceiling_conflict = copy.deepcopy(self.request)
        ceiling_conflict["execution_context"]["budget"]["tokens"] = 81
        self.assert_error(self.resolve(ceiling_conflict), "constraint_conflict")

    def test_resolution_is_deterministic_and_has_complete_provenance(self):
        first = self.resolve()
        second = self.resolve()
        self.assertEqual(first, second)
        for field in ("run_id", "task_ref.id", "task_ref.revision", "task_ref.sha256", "model", "mode", "context_policy", "budget", "verification_policy"):
            self.assertIn(field, first["provenance"])
        self.assertEqual(first["provenance"]["task_ref.id"]["source"], "task_derived")
        self.assertEqual(first["provenance"]["mode"]["source"], "mode_default")
        self.assertEqual(len(first["applied_restrictions"]), 3)

    def test_model_parameters_are_structurally_non_sensitive(self):
        safe = copy.deepcopy(self.request)
        safe["requested_overrides"] = {"model": {"parameters": {"temperature": 0.5, "retries": 2, "stream": False}}}
        self.assertEqual(self.resolve(safe)["run_config"]["model"]["parameters"], safe["requested_overrides"]["model"]["parameters"])
        for name, value in (
            ("api_key", "abc"),
            ("neutral", "plain-text-value"),
            ("unmarked_parameter", "eyJhbGciOiJIUzI1NiJ9"),
            ("temperature", [0.5]),
            ("temperature", {"nested": 0.5}),
            ("temperature", None),
            ("unknown-parameter", 1),
        ):
            request = copy.deepcopy(self.request)
            request["requested_overrides"] = {"model": {"parameters": {name: value}}}
            result = self.resolve(request)
            with self.subTest(name=name, value_type=type(value).__name__):
                self.assert_error(result, "invalid_request")
                self.assertNotIn(str(value), json.dumps(result))
        bypass = copy.deepcopy(self.request)
        bypass["execution_context"]["model"]["parameters"] = {"unmarked_parameter": "opaque-value"}
        result = self.resolve(bypass)
        self.assert_error(result, "invalid_request")
        self.assertNotIn("opaque-value", json.dumps(result))

    def test_tool_capability_is_not_an_input_or_authorization(self):
        request = copy.deepcopy(self.request)
        request["tool_capability"] = {"name": "anything"}
        self.assert_error(self.resolve(request), "invalid_request")

    def test_resolver_calls_no_execution_surface(self):
        with patch.object(subprocess, "run", side_effect=AssertionError("subprocess called")), patch.object(os, "system", side_effect=AssertionError("shell called")), patch.object(socket, "socket", side_effect=AssertionError("network called")):
            result = self.resolve()
        self.assertIn("run_config", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
