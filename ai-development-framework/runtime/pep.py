"""PEP H3-01: revalidate H2-02 objects immediately before one local read."""
import hashlib
import json
import time

from .local_read_runtime import receipt_for
from .contracts import valid


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def _hashed(value, field):
    return isinstance(value, dict) and value.get(field) == _digest({key: item for key, item in value.items() if key != field})


def _deny(decision, descriptor, reason_code):
    if not isinstance(decision, dict) or not isinstance(descriptor, dict):
        return {"result_version": "1.0", "outcome": "deny", "reason_code": reason_code, "bytes_read": 0, "taint": {"classification": "untrusted_workspace_file", "cannot_authorize": True}, "provenance": {"runtime_version": "1.0", "workspace_id": "unbound", "snapshot_digest": "0" * 64}}, None
    result = {"result_version": "1.0", "outcome": "deny", "reason_code": reason_code, "bytes_read": 0, "taint": {"classification": "untrusted_workspace_file", "cannot_authorize": True}, "provenance": {"runtime_version": "1.0", "workspace_id": descriptor.get("workspace_id", "unbound"), "snapshot_digest": descriptor.get("snapshot_digest", "0" * 64)}}
    try:
        return result, receipt_for(decision, descriptor, result)
    except (KeyError, TypeError):
        return result, None


class PolicyEnforcementPoint:
    """Consumes an admission once; it is not a reusable grant or bearer token."""
    def __init__(self, workspace_manager, runtime):
        self._manager = workspace_manager
        self._runtime = runtime

    def enforce_read(self, decision, intent, profile, policy, context, descriptor, principal=None):
        if not all((valid("admission_decision", decision), valid("tool_call_intent", intent), valid("tool_profile", profile), valid("policy_bundle", policy), valid("policy_context", context), valid("runtime_workspace_descriptor", descriptor))):
            return _deny(None, None, "invalid_contract")
        # ADR 0014: an identity-bearing request is revalidated at effect time; local edges pass None.
        if principal is not None and not valid("caller_principal", principal):
            return _deny(decision, descriptor, "invalid_principal")
        if principal is not None and time.time() >= principal["expires_at"]:
            return _deny(decision, descriptor, "principal_expired")
        if not isinstance(decision, dict) or decision.get("outcome") != "admit_read":
            return _deny(decision, descriptor, "invalid_admission")
        if not all(isinstance(value, dict) for value in (intent, profile, policy, context, descriptor)):
            return _deny(decision, descriptor, "binding_mismatch")
        scope = intent.get("resource_scope")
        bindings = decision.get("bindings")
        if not isinstance(scope, dict) or set(scope) != {"kind", "path"} or scope.get("kind") != "filesystem" or intent.get("arguments") != {"path": scope.get("path")}:
            return _deny(decision, descriptor, "scope_binding_mismatch")
        if decision.get("intent_digest") != _digest(intent):
            return _deny(decision, descriptor, "intent_digest_mismatch")
        if not _hashed(profile, "profile_sha256"):
            return _deny(decision, descriptor, "profile_hash_mismatch")
        if not _hashed(policy, "policy_sha256"):
            return _deny(decision, descriptor, "policy_hash_mismatch")
        if not isinstance(bindings, dict) or bindings != {"profile_sha256": profile["profile_sha256"], "policy_sha256": policy["policy_sha256"], "run_id": intent.get("run_id"), "operation_id": intent.get("operation_id"), "effective_scope": scope, "max_output_bytes": intent.get("requested_budget", {}).get("max_output_bytes")} or decision.get("effective_scope") != scope:
            return _deny(decision, descriptor, "binding_mismatch")
        if context.get("resolved_run_config_ref", {}).get("run_id") != intent.get("run_id") or context.get("policy_ref") != intent.get("policy_context_ref") or context.get("policy_ref", {}).get("policy_sha256") != policy["policy_sha256"]:
            return _deny(decision, descriptor, "run_binding_mismatch")
        if context.get("runtime_capability", {}).get("demonstrated") is not True or context.get("runtime_capability", {}).get("allowed_effect_classes") != ["read"]:
            return _deny(decision, descriptor, "runtime_capability_mismatch")
        operations = [item for item in profile.get("operations", []) if item.get("operation_id") == intent.get("operation_id")]
        if len(operations) != 1 or operations[0].get("effect_classes") != ["read"] or operations[0].get("resource_kind") != "filesystem" or scope not in operations[0].get("supported_scopes", []):
            return _deny(decision, descriptor, "operation_binding_mismatch")
        ceilings = [operations[0].get("max_risk", {}).get("max_output_bytes")]
        rules = [item for item in policy.get("rules", []) if item.get("operation_id") == intent.get("operation_id") and item.get("profile_sha256") == profile["profile_sha256"]]
        if len(rules) != 1 or scope not in rules[0].get("allowed_scopes", []) or rules[0].get("allowed_effect_classes") != ["read"]:
            return _deny(decision, descriptor, "policy_binding_mismatch")
        ceilings.append(rules[0].get("max_output_bytes"))
        for key in ("organizational_constraints", "repository_constraints", "mode_constraints"):
            constraint = context.get(key, {})
            if constraint.get("allowed_effect_classes") != ["read"] or scope not in constraint.get("allowed_scopes", []):
                return _deny(decision, descriptor, "policy_binding_mismatch")
            ceilings.append(constraint.get("max_output_bytes"))
        budget = intent.get("requested_budget", {}).get("max_output_bytes")
        if not isinstance(budget, int) or budget < 0 or any(not isinstance(value, int) for value in ceilings) or budget != min([budget, *ceilings]):
            return _deny(decision, descriptor, "budget_binding_mismatch")
        if descriptor.get("task_ref") != intent.get("task_ref") or descriptor.get("snapshot_digest") != intent.get("task_ref"):
            return _deny(decision, descriptor, "task_ref_mismatch")
        if not self._manager.validate_descriptor(descriptor):
            return _deny(decision, descriptor, "workspace_binding_mismatch")
        result = self._runtime.read(descriptor, scope["path"], budget)
        receipt = receipt_for(decision, descriptor, result)
        self._manager.mark_pending_cleanup(descriptor)
        return result, receipt
