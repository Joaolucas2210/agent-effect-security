"""Pure H4-01b aggregation of already-recorded, redacted evidence."""
import hashlib
import json

from jsonschema import Draft7Validator
from referencing import Registry, Resource

from integration.local_evidence_bundle import verify_offline


CANONICALIZATION = "json-c14n-v1"
_CATEGORIES = ("binding_mismatch", "sensitive_path_denied", "invalid_contract", "other")
_REQUIRED_SCHEMAS = {"evidence_bundle", "runtime_audit_receipt", "evidence_trial_observation", "evidence_trial_report"}
_METRIC_OUTCOMES = {"admit_read", "deny"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _valid(value, schema, store=None):
    if schema is None:
        return False
    registry = Registry()
    for uri, resource in (store or {}).items():
        registry = registry.with_resource(uri, Resource.from_contents(resource))
    return Draft7Validator(schema, registry=registry).is_valid(value)


def _schemas_valid(schemas):
    return isinstance(schemas, dict) and _REQUIRED_SCHEMAS <= set(schemas) and all(isinstance(schemas[key], dict) for key in _REQUIRED_SCHEMAS)


def _mapping_valid(mapping):
    return isinstance(mapping, dict) and set(mapping) == {"mapping_version", "categories", "h2_reason_codes", "h3_reason_codes"} and mapping["mapping_version"] == "1.0" and mapping["categories"] == list(_CATEGORIES) and all(isinstance(mapping[key], dict) and mapping[key] and all(isinstance(code, str) and category in _CATEGORIES for code, category in mapping[key].items()) for key in ("h2_reason_codes", "h3_reason_codes"))


def _report_payload(report):
    return {key: ({item: value for item, value in report[key].items() if item != "report_sha256"} if key == "verification" else value) for key, value in report.items()}


def _context_valid(context, schemas):
    if not isinstance(context, dict) or set(context) != {"report_id", "created_at", "provenance"}:
        return False
    probe = {"schema_version": "1.0", **context, "trial_count": 0, "observations_total": 0, "evidence_bundle_valid_total": 0, "evidence_bundle_invalid_total": 0, "decisions_total": 0, "admit_read_total": 0, "deny_total": 0, "binding_mismatch_total": 0, "sensitive_path_denied_total": 0, "invalid_contract_total": 0, "human_intervention_required_total": 0, "decision_latency_ms": {"count": 0, "sum": 0, "min": None, "max": None}, "verification": {"verification_version": "1.0", "canonicalization": CANONICALIZATION, "report_sha256": "0" * 64}}
    return _valid(probe, schemas["evidence_trial_report"])


def _observation_valid(observation, schemas, mapping):
    if not _valid(observation, schemas["evidence_trial_observation"], {"evidence-bundle.schema.json": schemas["evidence_bundle"]}):
        return False
    bundle = observation["evidence_bundle"]
    if not verify_offline(bundle, schemas) or bundle["reason_code"] not in mapping["h2_reason_codes"]:
        return False
    if bundle["decision_outcome"] not in _METRIC_OUTCOMES:
        return False
    if bundle["decision_outcome"] != "admit_read":
        return observation["runtime_outcome"] == "not_attempted" and observation["runtime_reason_code"] is None
    receipt = bundle["receipt"]
    return observation["runtime_outcome"] == receipt["outcome"] and observation["runtime_reason_code"] == receipt["reason_code"] and receipt["reason_code"] in mapping["h3_reason_codes"]


def _increment_category(report, category):
    if category != "other":
        report[f"{category}_total"] += 1


def aggregate_trial_observations(observations, report_context, schemas, reason_code_mapping):
    """Aggregate only verified facts; invalid inputs contribute one invalid count."""
    if not isinstance(observations, list) or not _schemas_valid(schemas) or not _mapping_valid(reason_code_mapping) or not _context_valid(report_context, schemas):
        raise ValueError("invalid_trial_metrics_input")
    report = {"schema_version": "1.0", **report_context, "trial_count": 0, "observations_total": len(observations), "evidence_bundle_valid_total": 0, "evidence_bundle_invalid_total": 0, "decisions_total": 0, "admit_read_total": 0, "deny_total": 0, "binding_mismatch_total": 0, "sensitive_path_denied_total": 0, "invalid_contract_total": 0, "human_intervention_required_total": 0, "decision_latency_ms": {"count": 0, "sum": 0, "min": None, "max": None}, "verification": {"verification_version": "1.0", "canonicalization": CANONICALIZATION, "report_sha256": ""}}
    seen_trials, seen_observations, latencies = set(), set(), []
    for observation in observations:
        duplicate = isinstance(observation, dict) and (observation.get("trial_id") in seen_trials or observation.get("observation_id") in seen_observations)
        if duplicate or not _observation_valid(observation, schemas, reason_code_mapping):
            report["evidence_bundle_invalid_total"] += 1
            continue
        seen_trials.add(observation["trial_id"])
        seen_observations.add(observation["observation_id"])
        bundle = observation["evidence_bundle"]
        report["evidence_bundle_valid_total"] += 1
        report["trial_count"] += 1
        report["decisions_total"] += 1
        if bundle["decision_outcome"] == "admit_read":
            report["admit_read_total"] += 1
            _increment_category(report, reason_code_mapping["h3_reason_codes"][observation["runtime_reason_code"]])
        elif bundle["decision_outcome"] == "deny":
            report["deny_total"] += 1
            _increment_category(report, reason_code_mapping["h2_reason_codes"][bundle["reason_code"]])
        if observation["human_intervention_required"]:
            report["human_intervention_required_total"] += 1
        latencies.append(observation["decision_latency_ms"])
    report["decision_latency_ms"] = {"count": len(latencies), "sum": sum(latencies), "min": min(latencies) if latencies else None, "max": max(latencies) if latencies else None}
    report["verification"]["report_sha256"] = digest(_report_payload(report))
    return json.loads(canonical(report))


def _report_invariants_valid(report):
    valid = report["evidence_bundle_valid_total"]
    decisions = report["decisions_total"]
    if report["observations_total"] != valid + report["evidence_bundle_invalid_total"] or report["trial_count"] != valid or decisions != valid or decisions != report["admit_read_total"] + report["deny_total"]:
        return False
    categories = ("binding_mismatch_total", "sensitive_path_denied_total", "invalid_contract_total")
    if any(report[field] > decisions for field in (*categories, "human_intervention_required_total")) or sum(report[field] for field in categories) > decisions or report["sensitive_path_denied_total"] > report["admit_read_total"]:
        return False
    latency = report["decision_latency_ms"]
    if latency["count"] != valid:
        return False
    if latency["count"] == 0:
        return (latency["sum"], latency["min"], latency["max"]) == (0, None, None)
    return latency["min"] is not None and latency["max"] is not None and latency["min"] <= latency["max"] and latency["count"] * latency["min"] <= latency["sum"] <= latency["count"] * latency["max"]


def verify_trial_report(report, schemas):
    """Purely validate the report contract, integrity digest, and aggregate invariants."""
    if not _schemas_valid(schemas) or not _valid(report, schemas["evidence_trial_report"]):
        return False
    if not _report_invariants_valid(report):
        return False
    return report["verification"]["canonicalization"] == CANONICALIZATION and report["verification"]["report_sha256"] == digest(_report_payload(report))
