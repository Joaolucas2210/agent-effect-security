"""Cached, local-only Draft-07 validators for H3-01 memory objects."""
import json
from pathlib import Path

from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError


_ROOT = Path(__file__).resolve().parent
_SCHEMAS = {
    "admission_decision": _ROOT.parent / "tools/v1/schemas/admission-decision.schema.json",
    "tool_call_intent": _ROOT.parent / "tools/v1/schemas/tool-call-intent.schema.json",
    "tool_profile": _ROOT.parent / "tools/v1/schemas/tool-profile.schema.json",
    "policy_bundle": _ROOT.parent / "tools/v1/schemas/policy-bundle.schema.json",
    "policy_context": _ROOT.parent / "tools/v1/schemas/policy-context.schema.json",
    "runtime_workspace_descriptor": _ROOT / "v1/schemas/runtime-workspace-descriptor.schema.json",
    "runtime_audit_receipt": _ROOT / "v1/schemas/runtime-audit-receipt.schema.json",
    "caller_principal": _ROOT.parent / "integration/v1/schemas/caller-principal.schema.json",
}


def _local_refs(value):
    if isinstance(value, dict):
        if "$ref" in value and (not isinstance(value["$ref"], str) or not value["$ref"].startswith("#")):
            return False
        return all(_local_refs(item) for item in value.values())
    if isinstance(value, list):
        return all(_local_refs(item) for item in value)
    return True


def _load_validators():
    try:
        schemas = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in _SCHEMAS.items()}
        if not all(_local_refs(schema) for schema in schemas.values()):
            return {}
        for schema in schemas.values():
            Draft7Validator.check_schema(schema)
        return {name: Draft7Validator(schema) for name, schema in schemas.items()}
    except (OSError, ValueError, SchemaError):
        return {}


_VALIDATORS = _load_validators()


def valid(contract, value):
    validator = _VALIDATORS.get(contract)
    try:
        return validator is not None and not any(validator.iter_errors(value))
    except Exception:
        return False
