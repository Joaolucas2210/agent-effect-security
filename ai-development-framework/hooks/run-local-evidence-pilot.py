#!/usr/bin/env python3
"""Run three isolated H4 evidence trials from trusted internal revisions."""
import copy
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from integration.evidence_trial_metrics import aggregate_trial_observations, verify_trial_report
from integration.local_evidence_bundle import compose, digest
from runtime.local_read_runtime import LocalReadRuntime
from runtime.pep import PolicyEnforcementPoint
from runtime.workspace_manager import WORKSPACE_FAILURE_CODES, WorkspaceManager


ROOT = Path(__file__).resolve().parent.parent
TRUSTED_REPOSITORY = ROOT.parent
TRIALS = (
    ("pilot-admit", "HEAD", "README.md", False),
    ("pilot-deny", "HEAD~1", "README.md", True),
    ("pilot-sensitive", "HEAD~2", "secrets/token", False),
)
_PUBLIC_FAILURES = {"pilot_workspace_prepare_failed", "pilot_snapshot_binding_failed", "pilot_workspace_cleanup_failed", "pilot_execution_failed", "pilot_report_verification_failed"}


def _load(path): return json.loads(path.read_text())
def _timestamp(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def _rehash(value, field): value[field] = digest({key: item for key, item in value.items() if key != field})
def _workspace_failure(exc, fallback): return exc.args[0] if isinstance(exc, RuntimeError) and len(exc.args) == 1 and exc.args[0] in WORKSPACE_FAILURE_CODES else fallback


def _schemas():
    h2, h3, h4 = ROOT / "tools/v1/schemas", ROOT / "runtime/v1/schemas", ROOT / "integration/v1/schemas"
    names = {
        "tool_profile": h2 / "tool-profile.schema.json", "tool_call_intent": h2 / "tool-call-intent.schema.json", "policy_bundle": h2 / "policy-bundle.schema.json", "policy_context": h2 / "policy-context.schema.json", "runtime_workspace_descriptor": h3 / "runtime-workspace-descriptor.schema.json", "runtime_audit_receipt": h3 / "runtime-audit-receipt.schema.json", "read_result": h3 / "read-result.schema.json", "adapter_request": h4 / "adapter-request.schema.json", "evidence_bundle": h4 / "evidence-bundle.schema.json", "evidence_trial_observation": h4 / "evidence-trial-observation.schema.json", "evidence_trial_report": h4 / "evidence-trial-report.schema.json", "admission_decision": h2 / "admission-decision.schema.json", "list_files_input": h2 / "list-files-input.schema.json",
    }
    return {name: _load(path) for name, path in names.items()}


def _request(descriptor, run_id, path, deny):
    examples = ROOT / "tools/v1/examples"
    profile, policy = _load(examples / "tool-profile/valid/read-worktree.json"), _load(examples / "policy-bundle/valid/read-worktree.json")
    context, intent = _load(examples / "policy-context/valid/read-worktree.json"), _load(examples / "tool-call-intent/valid/read-worktree.json")
    scope, budget = {"kind": "filesystem", "path": path}, 64
    profile["operations"][0].update(supported_scopes=[scope], max_risk={"level": "low", "max_output_bytes": budget}); _rehash(profile, "profile_sha256")
    policy["rules"][0].update(profile_sha256=profile["profile_sha256"], allowed_scopes=[scope], max_output_bytes=budget); _rehash(policy, "policy_sha256")
    for name in ("organizational_constraints", "repository_constraints", "mode_constraints"): context[name].update(allowed_scopes=[scope], max_output_bytes=budget)
    context["resolved_run_config_ref"]["run_id"] = run_id; context["policy_ref"] = {"policy_id": policy["policy_id"], "policy_sha256": policy["policy_sha256"]}
    if deny: context["runtime_capability"]["demonstrated"] = False
    intent.update(run_id=run_id, task_ref=descriptor["snapshot_digest"], resource_scope=scope, arguments={"path": path}, requested_budget={"max_output_bytes": budget}, policy_context_ref=copy.deepcopy(context["policy_ref"]))
    intent["tool_ref"]["profile_sha256"] = profile["profile_sha256"]
    return {"schema_version": "1.0", "adapter_id": "local-adapter", "created_at": _timestamp(), "intent": intent, "profiles": [profile], "policy": policy, "context": context, "workspace": descriptor, "provenance": {"adapter_version": "1.0", "kind": "local_structured_adapter"}}


def _trial(schemas, run_id, revision, path, deny):
    manager = descriptor = None
    try:
        manager = WorkspaceManager(TRUSTED_REPOSITORY, revision); descriptor = manager.prepare(run_id)
    except Exception as exc:
        raise RuntimeError(_workspace_failure(exc, "pilot_workspace_prepare_failed")) from None
    try:
        request = _request(descriptor, run_id, path, deny)
        if descriptor["task_ref"] != descriptor["snapshot_digest"] or request["intent"]["task_ref"] != descriptor["snapshot_digest"]: raise RuntimeError("pilot_snapshot_binding_failed")
        started = time.monotonic(); pep = PolicyEnforcementPoint(manager, LocalReadRuntime(_load(ROOT / "runtime/v1/policies/sensitive-path-policy-v1.json")))
        bundle = compose(request, schemas, pep)
        outcome, reason = (bundle["receipt"]["outcome"], bundle["receipt"]["reason_code"]) if bundle["decision_outcome"] == "admit_read" else ("not_attempted", None)
        observation = {"schema_version": "1.0", "observation_id": f"observation-{run_id}", "trial_id": f"trial-{run_id}", "observed_at": _timestamp(), "evidence_bundle": bundle, "runtime_outcome": outcome, "runtime_reason_code": reason, "human_intervention_required": False, "decision_latency_ms": int((time.monotonic() - started) * 1000), "provenance": {"collector_version": "1.0", "kind": "local_trial_observation"}}
        return observation, {"workspace_id": descriptor["workspace_id"], "snapshot_digest": descriptor["snapshot_digest"], "task_ref": descriptor["task_ref"], "intent_task_ref": request["intent"]["task_ref"]}
    except RuntimeError: raise
    except Exception: raise RuntimeError("pilot_execution_failed") from None
    finally:
        if descriptor is not None:
            try:
                if not manager.cleanup(descriptor["workspace_id"]): raise RuntimeError("cleanup_failed")
            except Exception as exc: raise RuntimeError(_workspace_failure(exc, "pilot_workspace_cleanup_failed")) from None


def _trials(schemas):
    observations, identities = zip(*[_trial(schemas, *trial) for trial in TRIALS])
    if len({item["workspace_id"] for item in identities}) != 3 or len({item["snapshot_digest"] for item in identities}) != 3: raise RuntimeError("pilot_snapshot_binding_failed")
    return list(observations), list(identities)


def run_pilot():
    schemas = _schemas(); observations, _ = _trials(schemas)
    report = aggregate_trial_observations(observations, {"report_id": "local-evidence-pilot", "created_at": _timestamp(), "provenance": {"aggregator_version": "1.0", "kind": "local_evidence_trial_metrics"}}, schemas, _load(ROOT / "integration/v1/policies/evidence-metric-reason-codes-v1.json"))
    if not verify_trial_report(report, schemas): raise RuntimeError("pilot_report_verification_failed")
    return report


def main():
    try:
        print(json.dumps(run_pilot(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)); return 0
    except RuntimeError as exc:
        code = exc.args[0] if len(exc.args) == 1 else None
        print(code if code in _PUBLIC_FAILURES or code in WORKSPACE_FAILURE_CODES else "pilot_execution_failed"); return 1
    except Exception:
        print("pilot_execution_failed"); return 1


if __name__ == "__main__": raise SystemExit(main())
