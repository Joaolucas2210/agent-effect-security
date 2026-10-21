"""Host-declared external assessment; integrity is not evaluator attestation."""
import json
from pathlib import Path

from jsonschema import Draft7Validator

from integration.local_evidence_bundle import digest
from integration.session_trial import verify_session_report

_SCHEMA = json.loads((Path(__file__).parent / "v2/schemas/task-evaluation.schema.json").read_text(encoding="utf-8"))


def _hash(record):
    return digest({"domain": "task-evaluation-v1", "evaluation": {
        key: value for key, value in record.items() if key != "verification"
    }})


def _binding(report):
    return {
        **{key: report[key] for key in ("trial_id", "task_id", "session_id")},
        "report_sha256": report["verification"]["report_sha256"],
        "acceptance_sha256": report["provenance"]["acceptance_sha256"],
        "initial_revision_sha": report["provenance"]["revision_sha"],
    }


def build_task_evaluation(report, *, evaluator_id, evaluator_version, evaluated_revision_sha,
                          task_outcome, result_sha256, created_at):
    """Record an assessor's result digest; never execute or infer an assessment."""
    if not verify_session_report(report) or "provenance" not in report:
        raise ValueError("invalid_task_evaluation_input")
    record = {
        "schema_version": "1.0", **_binding(report), "evaluator_id": evaluator_id,
        "evaluator_version": evaluator_version, "evaluated_revision_sha": evaluated_revision_sha,
        "task_outcome": task_outcome, "result_sha256": result_sha256, "created_at": created_at,
    }
    record["verification"] = {"canonicalization": "json-c14n-v1", "evaluation_sha256": _hash(record)}
    if not verify_task_evaluation(record, report):
        raise ValueError("invalid_task_evaluation_input")
    return record


def verify_task_evaluation(record, report):
    """Verify closed shape, digest and exact session binding, not truth of success."""
    try:
        return (
            verify_session_report(report)
            and Draft7Validator(_SCHEMA).is_valid(record)
            and record["verification"]["evaluation_sha256"] == _hash(record)
            and all(record[key] == value for key, value in _binding(report).items())
        )
    except (KeyError, TypeError, ValueError):
        return False
