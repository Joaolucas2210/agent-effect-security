"""Pure, deterministic H2-02 local tool-admission decision point."""
import hashlib
import json
import re

from jsonschema import Draft7Validator


_HASH = re.compile(r"[a-f0-9]{64}\Z")
_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_HOST = re.compile(r"[a-z0-9][a-z0-9.-]{0,252}\Z")
_SENSITIVE = re.compile(r"(?:secret|password|credential|api[_-]?key|token)", re.I)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _hash_valid(value, field):
    copy = dict(value)
    copy.pop(field, None)
    return value.get(field) == _digest(copy)


def _valid(value, schema):
    return schema is not None and Draft7Validator(schema).is_valid(value)


def _normal_scope(scope):
    if not isinstance(scope, dict):
        return None
    kind = scope.get("kind")
    if kind == "filesystem":
        path = scope.get("path")
        if not isinstance(path, str) or not path or path.startswith("/") or "\x00" in path or not _PATH.fullmatch(path):
            return None
        if any(part in {"..", ".git", ".env"} for part in path.split("/")):
            return None
        return {"kind": kind, "path": path}
    if kind == "network":
        scheme, host, port = scope.get("scheme"), scope.get("hostname"), scope.get("port")
        if scheme not in {"http", "https"} or not isinstance(host, str) or host != host.lower() or ".." in host or not _HOST.fullmatch(host) or type(port) is not int or not 1 <= port <= 65535:
            return None
        return {"kind": kind, "scheme": scheme, "hostname": host, "port": port}
    if kind == "repository" and isinstance(scope.get("revision"), str) and _HASH.fullmatch(scope["revision"]):
        return {"kind": kind, "revision": scope["revision"]}
    return None


def _bindings(intent=None, profile=None, policy=None, scope=None, budget=None):
    return {
        "profile_sha256": profile.get("profile_sha256") if profile else None,
        "policy_sha256": policy.get("policy_sha256") if policy else None,
        "run_id": intent.get("run_id") if intent else None,
        "operation_id": intent.get("operation_id") if intent else None,
        "effective_scope": scope,
        "max_output_bytes": budget,
    }


def _decision(code, intent=None, profile=None, policy=None, scope=None, budget=None, rules=(), digest=None):
    result = {
        "decision_version": "1.0",
        "decision_id": "",
        "outcome": "deny",
        "stable_reason_code": code,
        "applied_rule_ids": sorted(set(rules)),
        "intent_digest": digest,
        "effective_scope": scope,
        "bindings": _bindings(intent, profile, policy, scope, budget),
        "provenance": {"pdp_version": "1.0", "kind": "local_pure_pdp"},
    }
    result["decision_id"] = _digest({key: value for key, value in result.items() if key != "decision_id"})
    return json.loads(_canonical(result))


def decide(intent, profiles, policy, context, schemas, principal=None):
    """Return one canonical AdmissionDecision; this function never executes a tool.

    `principal` (CallerPrincipal, ADR 0014) is optional: when present it must be valid, but v1
    host policy decides without its fields, so it never opens an effect. No clock here (pure)."""
    required = {"tool_profile", "tool_call_intent", "policy_bundle", "policy_context", "admission_decision", "list_files_input"}
    if not isinstance(schemas, dict) or required - set(schemas):
        return _decision("pdp_configuration_error")
    if not _valid(intent, schemas["tool_call_intent"]):
        return _decision("invalid_intent")
    if principal is not None and not _valid(principal, schemas.get("caller_principal")):
        return _decision("invalid_principal", intent=intent)
    if not isinstance(profiles, list) or not all(_valid(item, schemas["tool_profile"]) for item in profiles):
        return _decision("invalid_registry", intent=intent)
    if not _valid(policy, schemas["policy_bundle"]):
        return _decision("invalid_policy", intent=intent)
    if not _valid(context, schemas["policy_context"]):
        return _decision("invalid_policy_context", intent=intent, policy=policy)
    tool_profiles = [item for item in profiles if item["tool_id"] == intent["tool_ref"]["tool_id"]]
    if not profiles:
        return _decision("unknown_profile", intent=intent, policy=policy)
    if not tool_profiles:
        return _decision("unknown_tool", intent=intent, policy=policy)
    profile_matches = [item for item in tool_profiles if item["profile_sha256"] == intent["tool_ref"]["profile_sha256"]]
    if len(profile_matches) != 1:
        return _decision("profile_hash_mismatch", intent=intent, policy=policy)
    profile = profile_matches[0]
    if not _hash_valid(profile, "profile_sha256"):
        return _decision("profile_hash_mismatch", intent=intent, profile=profile, policy=policy)
    operation_matches = [item for item in profile["operations"] if item["operation_id"] == intent["operation_id"]]
    if len(operation_matches) != 1:
        return _decision("unknown_operation", intent=intent, profile=profile, policy=policy)
    operation = operation_matches[0]
    if any(_SENSITIVE.search(str(key)) for key in intent["arguments"]):
        return _decision("sensitive_argument_rejected", intent=intent, profile=profile, policy=policy)
    if operation["input_schema_ref"] != "list-files-input.schema.json" or not _valid(intent["arguments"], schemas["list_files_input"]):
        return _decision("invalid_arguments", intent=intent, profile=profile, policy=policy)
    scope = _normal_scope(intent["resource_scope"])
    if scope is None or scope["kind"] != operation["resource_kind"] or intent["arguments"].get("path") != scope.get("path"):
        return _decision("invalid_scope", intent=intent, profile=profile, policy=policy)
    if not _hash_valid(policy, "policy_sha256"):
        return _decision("policy_hash_mismatch", intent=intent, profile=profile, policy=policy)
    if context["policy_ref"]["policy_id"] != policy["policy_id"] or intent["policy_context_ref"]["policy_id"] != policy["policy_id"]:
        return _decision("unknown_policy", intent=intent, profile=profile, policy=policy)
    if context["policy_ref"] != {"policy_id": policy["policy_id"], "policy_sha256": policy["policy_sha256"]} or intent["policy_context_ref"] != context["policy_ref"]:
        return _decision("policy_binding_mismatch", intent=intent, profile=profile, policy=policy)
    if intent["run_id"] != context["resolved_run_config_ref"]["run_id"]:
        return _decision("run_binding_mismatch", intent=intent, profile=profile, policy=policy)
    rule_matches = [item for item in policy["rules"] if all((item["tool_id"] == profile["tool_id"], item["profile_sha256"] == profile["profile_sha256"], item["operation_id"] == operation["operation_id"]))]
    if len(rule_matches) != 1:
        return _decision("unknown_policy_rule", intent=intent, profile=profile, policy=policy, scope=scope)
    rule = rule_matches[0]
    rules = [rule["rule_id"], context["organizational_constraints"]["rule_id"], context["repository_constraints"]["rule_id"], context["runtime_capability"]["rule_id"], context["mode_constraints"]["rule_id"]]
    effects = set(operation["effect_classes"])
    if effects != {"read"}:
        return _decision("effect_not_supported_in_h2_02", intent, profile, policy, scope, rules=rules)
    if not context["runtime_capability"]["demonstrated"] or "read" not in context["runtime_capability"]["allowed_effect_classes"]:
        return _decision("runtime_capability_not_demonstrated", intent, profile, policy, scope, rules=rules)
    restrictions = (rule, context["organizational_constraints"], context["repository_constraints"], context["mode_constraints"])
    if any("read" not in item["allowed_effect_classes"] for item in restrictions):
        return _decision("effect_not_allowlisted", intent, profile, policy, scope, rules=rules)
    if any(scope not in item["allowed_scopes"] for item in restrictions) or scope not in operation["supported_scopes"]:
        return _decision("scope_not_allowlisted", intent, profile, policy, scope, rules=rules)
    # ADR 0024: a policy that names principals is closed to anyone it does not name; the host allowlist above
    # stays the ceiling, the principal's list can only narrow it. A policy without principal_rules is unchanged.
    principal_rules = policy.get("principal_rules")
    if principal_rules is not None:
        if principal is None:
            return _decision("principal_required", intent, profile, policy, scope, rules=rules)
        principal_matches = [item for item in principal_rules if item["sub"] == principal["sub"]]
        if len(principal_matches) != 1:
            return _decision("principal_not_allowlisted", intent, profile, policy, scope, rules=rules)
        if scope not in principal_matches[0]["allowed_scopes"]:
            return _decision("scope_not_allowlisted_for_principal", intent, profile, policy, scope, rules=rules)
        rules = rules + [f"principal:{principal['sub']}"]
    budget = min([intent["requested_budget"]["max_output_bytes"], operation["max_risk"]["max_output_bytes"]] + [item["max_output_bytes"] for item in restrictions])
    if intent["requested_budget"]["max_output_bytes"] > budget:
        return _decision("budget_exceeds_ceiling", intent, profile, policy, scope, budget, rules)
    digest = _digest(intent)
    result = _decision("admit_read", intent, profile, policy, scope, budget, rules, digest)
    result["outcome"] = "admit_read"
    result["decision_id"] = _digest({key: value for key, value in result.items() if key != "decision_id"})
    return json.loads(_canonical(result))
