"""H4-01 composition and offline verification; no policy or runtime is implemented here."""
import hashlib
import json

from jsonschema import Draft7Validator

from tools.pdp import decide


CANONICALIZATION = "json-c14n-v1"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _valid(value, schema):
    return schema is not None and Draft7Validator(schema).is_valid(value)


def _bundle_payload(bundle, include_id=False):
    payload = {key: value for key, value in bundle.items() if include_id or key != "bundle_id"}
    payload["verification"] = {key: value for key, value in payload["verification"].items() if key != "bundle_sha256"}
    return payload


def _receipt_valid(receipt, schema):
    return _valid(receipt, schema) and receipt["receipt_id"] == digest({key: value for key, value in receipt.items() if key != "receipt_id"})


def _read_projection(result):
    return {
        "result_version": result["result_version"], "outcome": result["outcome"],
        "reason_code": result["reason_code"], "bytes_read": result["bytes_read"],
        "taint": result["taint"], "provenance": result["provenance"],
        **({"content_sha256": result["content_sha256"]} if "content_sha256" in result else {}),
    }


def _bundle(request, decision, result=None, receipt=None):
    bindings = decision["bindings"]
    bundle = {
        "schema_version": "1.0", "bundle_id": "", "run_id": bindings["run_id"],
        "adapter_id": request["adapter_id"], "created_at": request["created_at"],
        "decision_id": decision["decision_id"], "decision_outcome": decision["outcome"],
        "reason_code": decision["stable_reason_code"], "profile_sha256": bindings["profile_sha256"],
        "policy_sha256": bindings["policy_sha256"], "intent_digest": decision["intent_digest"],
        "operation_id": bindings["operation_id"], "effective_scope": bindings["effective_scope"],
        "workspace_id": request["workspace"]["workspace_id"],
        "snapshot_digest": request["workspace"]["snapshot_digest"],
        "read_result_digest": digest(_read_projection(result)) if result else None,
        "read_result_classification": result["taint"]["classification"] if result else None,
        "receipt": receipt, "verification": {"verification_version": "1.0", "canonicalization": CANONICALIZATION, "bundle_sha256": ""},
        "provenance": {"adapter_version": "1.0", "pdp_version": "1.0", "pep_version": "1.0" if result else "not_called", "kind": "local_evidence_composition"},
    }
    bundle["bundle_id"] = digest(_bundle_payload(bundle))
    bundle["verification"]["bundle_sha256"] = digest(_bundle_payload(bundle, include_id=True))
    return json.loads(canonical(bundle))


def compose(request, schemas, pep, *, decide_fn=None):
    """Compose H2-02 then H3-01; only the PEP owns the effectful read."""
    required = {"adapter_request", "evidence_bundle", "tool_profile", "tool_call_intent", "policy_bundle", "policy_context", "runtime_workspace_descriptor", "runtime_audit_receipt", "read_result", "admission_decision", "list_files_input"}
    if not isinstance(schemas, dict) or required - set(schemas) or not _valid(request, schemas["adapter_request"]):
        raise ValueError("invalid_adapter_request")
    if not all([_valid(request["intent"], schemas["tool_call_intent"]), _valid(request["policy"], schemas["policy_bundle"]), _valid(request["context"], schemas["policy_context"]), _valid(request["workspace"], schemas["runtime_workspace_descriptor"]), all(_valid(profile, schemas["tool_profile"]) for profile in request["profiles"])]):
        raise ValueError("invalid_referenced_contract")
    decision = (decide if decide_fn is None else decide_fn)(request["intent"], request["profiles"], request["policy"], request["context"], schemas)
    if decision["outcome"] != "admit_read":
        return _bundle(request, decision)
    profile = [item for item in request["profiles"] if item["tool_id"] == request["intent"]["tool_ref"]["tool_id"] and item["profile_sha256"] == request["intent"]["tool_ref"]["profile_sha256"]]
    result, receipt = pep.enforce_read(decision, request["intent"], profile[0], request["policy"], request["context"], request["workspace"])
    if not _valid(result, schemas["read_result"]) or result["taint"] != {"classification": "untrusted_workspace_file", "cannot_authorize": True} or not _receipt_valid(receipt, schemas["runtime_audit_receipt"]):
        raise ValueError("invalid_pep_result")
    return _bundle(request, decision, result, receipt)


def verify_offline(bundle, schemas):
    """Pure fail-closed verification. It verifies evidence, never grants authority."""
    if not isinstance(schemas, dict) or not _valid(bundle, schemas.get("evidence_bundle")):
        return False
    if bundle["verification"]["canonicalization"] != CANONICALIZATION:
        return False
    if bundle["bundle_id"] != digest(_bundle_payload(bundle)) or bundle["verification"]["bundle_sha256"] != digest(_bundle_payload(bundle, include_id=True)):
        return False
    receipt = bundle["receipt"]
    if bundle["decision_outcome"] != "admit_read":
        return receipt is None and bundle["read_result_digest"] is None and bundle["read_result_classification"] is None
    if not _receipt_valid(receipt, schemas.get("runtime_audit_receipt")):
        return False
    fields = ("decision_id", "run_id", "operation_id", "effective_scope", "profile_sha256", "policy_sha256", "workspace_id", "snapshot_digest")
    if any(receipt[field] != bundle[field] for field in fields):
        return False
    projection = {"result_version": "1.0", "outcome": receipt["outcome"], "reason_code": receipt["reason_code"], "bytes_read": receipt["bytes_read"], "taint": {"classification": bundle["read_result_classification"], "cannot_authorize": True}, "provenance": {"runtime_version": "1.0", "workspace_id": bundle["workspace_id"], "snapshot_digest": bundle["snapshot_digest"]}}
    if "content_sha256" in receipt:
        projection["content_sha256"] = receipt["content_sha256"]
    return bundle["read_result_digest"] == digest(projection)


def logical_replay(bundle):
    """Return a deterministic diagnostic chain only; it never re-evaluates or executes."""
    return {"replay_version": "1.0", "chain": [{"stage": "intent", "intent_digest": bundle["intent_digest"]}, {"stage": "pdp", "decision_id": bundle["decision_id"], "outcome": bundle["decision_outcome"], "reason_code": bundle["reason_code"]}, {"stage": "pep", "receipt_present": bundle["receipt"] is not None, "read_result_digest": bundle["read_result_digest"]}, {"stage": "evidence", "bundle_id": bundle["bundle_id"]}]}


def is_authorization(_bundle):
    """Evidence is never a bearer token or authorization input."""
    return False
