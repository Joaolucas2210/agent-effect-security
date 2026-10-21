"""P0-D session projection of verified local evidence; never an authorization input."""
import json
from collections import Counter, defaultdict
from pathlib import Path

from jsonschema import Draft7Validator
from referencing import Registry, Resource

from integration.adapter_attempt import verify_attempt
from integration.attempt_timing import STAGES, TIMING_SCHEMA, verify_timing
from integration.local_evidence_bundle import digest, verify_offline


_SCHEMA = json.loads((Path(__file__).parent / "v2/schemas/session-trial-report.schema.json").read_text(encoding="utf-8"))
_STAGES = STAGES
_REGISTRY = Registry().with_resource(TIMING_SCHEMA["$id"], Resource.from_contents(TIMING_SCHEMA))


def _payload(report):
    return {key: value for key, value in report.items() if key != "verification"}


def _hash(report):
    return digest({"domain": "session-trial-report-v2", "report": _payload(report)})


def _bundle_status(observation, verified, references):
    bundle_id = observation["bundle_id"]
    if bundle_id is None:
        return "none"
    if references[bundle_id] > 1:
        return "conflict"
    return "verified" if bundle_id in verified else "missing_or_invalid"


def _timing_stages(observations):
    summaries = {}
    for stage in STAGES:
        values = [item["timing"]["durations_ms"][stage] for item in observations if "timing" in item and item["timing"]["durations_ms"][stage] is not None]
        summaries[stage] = {"count": len(values), "sum": sum(values), "min": min(values) if values else None, "max": max(values) if values else None}
    return summaries


def _project_timings(observations, starts, records, session_id):
    counts = {key: 0 for key in ("observed_total", "invalid_total", "duplicates_total", "other_session_total", "conflicts_total", "uncorrelated_total")}
    counts["files_total"] = len(records)
    seen, groups = set(), defaultdict(list)
    by_id = {item["attempt_id"]: item for item in observations}
    for record in records:
        if not verify_timing(record):
            counts["invalid_total"] += 1
            continue
        if record["run_id"] != session_id:
            counts["other_session_total"] += 1
            continue
        attempt_id, fingerprint = record["attempt_id"], record["verification"]["record_sha256"]
        if attempt_id in starts and record["start_event_sha256"] != starts[attempt_id]:
            counts["invalid_total"] += 1
            continue
        if fingerprint in seen:
            counts["duplicates_total"] += 1
            continue
        seen.add(fingerprint)
        if attempt_id not in by_id or by_id[attempt_id]["capture_state"] == "invalid":
            counts["uncorrelated_total"] += 1
            continue
        groups[attempt_id].append(record)
    for attempt_id, candidates in groups.items():
        if len(candidates) != 1:
            counts["conflicts_total"] += len(candidates)
            continue
        by_id[attempt_id].update(start_event_sha256=starts[attempt_id], timing=candidates[0])
        counts["observed_total"] += 1
    return {**counts, "coverage": "observed" if counts["observed_total"] else "unknown", "stages": _timing_stages(observations)}


def build_session_report(trial_id, task_id, session_id, journals, bundles, schemas, created_at, *, timings=None, provenance=None):
    """Count only verifiable starts and bundles; old evidence has no measured durations."""
    if not isinstance(journals, list) or not isinstance(bundles, list) or not isinstance(schemas, dict) or {"adapter_attempt_event", "evidence_bundle", "runtime_audit_receipt"} - set(schemas):
        raise ValueError("invalid_session_trial_input")
    verified, invalid_bundles, duplicate_bundles = {}, 0, 0
    for bundle in bundles:
        try:
            if not verify_offline(bundle, schemas) or bundle["run_id"] != session_id:
                raise ValueError
            if bundle["bundle_id"] in verified:
                duplicate_bundles += 1
            else:
                verified[bundle["bundle_id"]] = bundle
        except Exception:
            invalid_bundles += 1
    observations, invalid_journals, seen_attempts = [], 0, {}
    duplicate_journals, other_sessions = 0, 0
    classified = [(events, verify_attempt(events, schemas["adapter_attempt_event"])) for events in journals]
    # Verify intact copies first so corrupt duplicates remain invalid in either file order.
    for events, state in sorted(classified, key=lambda item: item[1] == "invalid"):
        try:
            if not isinstance(events, list) or verify_attempt(events[:1], schemas["adapter_attempt_event"]) != "incomplete":
                raise ValueError
            start = events[0]
            if start["run_id"] != session_id:
                if state == "invalid":
                    raise ValueError
                other_sessions += 1
                continue
            if start["attempt_id"] in seen_attempts:
                if state == "invalid":
                    invalid_journals += 1
                else:
                    duplicate_journals += 1
                previous_events, observation = seen_attempts[start["attempt_id"]]
                if events != previous_events:
                    observation.update(capture_state="invalid", bundle_id=None)
                continue
            bundle_id = events[1]["payload"]["bundle_id"] if state == "complete" else None
            observation = {"attempt_id": start["attempt_id"], "capture_state": state, "bundle_id": bundle_id, "bundle_status": "none"}
            observations.append(observation)
            seen_attempts[start["attempt_id"]] = events, observation
        except Exception:
            invalid_journals += 1
    observations.sort(key=lambda value: value["attempt_id"])
    references = Counter(item["bundle_id"] for item in observations)
    for observation in observations:
        observation["bundle_status"] = _bundle_status(observation, verified, references)
    used = {item["bundle_id"] for item in observations if item["bundle_status"] == "verified"}
    if timings is None:
        timings = []
    if not isinstance(timings, list):
        raise ValueError("invalid_session_trial_input")
    starts = {attempt_id: events[0]["event_sha256"] for attempt_id, (events, _) in seen_attempts.items()}
    timing_projection = _project_timings(observations, starts, timings, session_id)
    report = {
        "schema_version": "2.0", "trial_id": trial_id, "task_id": task_id, "session_id": session_id,
        "created_at": created_at, "coverage": "observed" if observations else "unknown", "task_outcome": None,
        "journal_files_total": len(journals), "journal_invalid_total": invalid_journals,
        "journal_duplicates_total": duplicate_journals, "journal_other_session_total": other_sessions,
        "attempts_observed_total": len(observations),
        "attempt_complete_total": sum(item["capture_state"] == "complete" for item in observations),
        "attempt_incomplete_total": sum(item["capture_state"] == "incomplete" for item in observations),
        "attempt_invalid_total": sum(item["capture_state"] == "invalid" for item in observations),
        "bundle_files_total": len(bundles), "bundles_valid_total": len(verified), "bundles_invalid_total": invalid_bundles,
        "bundle_duplicates_total": duplicate_bundles,
        "orphan_bundles_total": len(set(verified) - used),
        "correlation_conflict_total": sum(item["bundle_status"] == "conflict" for item in observations),
        "verified_bundle_ids": sorted(verified), "observations": observations,
        "durations_ms": {stage: None for stage in _STAGES},
        "timings": timing_projection,
        "decisions": {
            "total": len(verified),
            "admit_read": sum(bundle["decision_outcome"] == "admit_read" for bundle in verified.values()),
            "deny": sum(bundle["decision_outcome"] == "deny" for bundle in verified.values()),
            "approval_required": sum(bundle["decision_outcome"] == "approval_required" for bundle in verified.values()),
            "runtime_delivered": sum(bundle["receipt"] is not None and bundle["receipt"]["outcome"] == "delivered" for bundle in verified.values()),
            "runtime_denied": sum(bundle["receipt"] is not None and bundle["receipt"]["outcome"] == "deny" for bundle in verified.values()),
        },
    }
    if provenance is not None:
        report["provenance"] = dict(provenance)
    report["verification"] = {"canonicalization": "json-c14n-v1", "report_sha256": _hash(report)}
    if not verify_session_report(report):
        raise ValueError("invalid_session_trial_input")
    return report


def verify_session_report(report):
    """Verify the closed shape, digest and counting invariants; never grant a read."""
    try:
        if not Draft7Validator(_SCHEMA, registry=_REGISTRY).is_valid(report) or report["verification"]["report_sha256"] != _hash(report):
            return False
        observations = report["observations"]
        ids = [item["attempt_id"] for item in observations]
        bundle_ids = report["verified_bundle_ids"]
        if ids != sorted(set(ids)) or bundle_ids != sorted(set(bundle_ids)):
            return False
        if report["coverage"] != ("observed" if observations else "unknown"):
            return False
        if report["journal_files_total"] != len(observations) + report["journal_invalid_total"] + report.get("journal_duplicates_total", 0) + report.get("journal_other_session_total", 0):
            return False
        if report["bundle_files_total"] != len(bundle_ids) + report["bundles_invalid_total"] + report.get("bundle_duplicates_total", 0):
            return False
        if report["attempts_observed_total"] != len(observations) or report["bundles_valid_total"] != len(bundle_ids):
            return False
        if any(report[f"attempt_{state}_total"] != sum(item["capture_state"] == state for item in observations) for state in ("complete", "incomplete", "invalid")):
            return False
        if "decisions" in report:
            decisions = report["decisions"]
            if decisions["total"] != len(bundle_ids) or decisions["total"] != decisions["admit_read"] + decisions["deny"] + decisions["approval_required"] or decisions["admit_read"] != decisions["runtime_delivered"] + decisions["runtime_denied"]:
                return False
        references = Counter(item["bundle_id"] for item in observations)
        used = set()
        for observation in observations:
            if "timing" in observation:
                timing = observation["timing"]
                if observation["capture_state"] == "invalid" or not verify_timing(timing) or timing["run_id"] != report["session_id"] or timing["attempt_id"] != observation["attempt_id"] or timing["start_event_sha256"] != observation.get("start_event_sha256"):
                    return False
            elif "start_event_sha256" in observation:
                return False
            if observation["capture_state"] != "complete" and observation["bundle_id"] is not None:
                return False
            expected = _bundle_status(observation, bundle_ids, references)
            if observation["bundle_status"] != expected:
                return False
            if expected == "verified":
                used.add(observation["bundle_id"])
        if "timings" in report:
            counts = report["timings"]
            if counts["observed_total"] != sum("timing" in item for item in observations) or counts["files_total"] != sum(counts[key] for key in ("observed_total", "invalid_total", "duplicates_total", "other_session_total", "conflicts_total", "uncorrelated_total")):
                return False
            if counts["coverage"] != ("observed" if counts["observed_total"] else "unknown") or counts["stages"] != _timing_stages(observations):
                return False
        elif any("timing" in item for item in observations):
            return False
        return report["orphan_bundles_total"] == len(set(bundle_ids) - used) and report["correlation_conflict_total"] == sum(item["bundle_status"] == "conflict" for item in observations)
    except Exception:
        return False
