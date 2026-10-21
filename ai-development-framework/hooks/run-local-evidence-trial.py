#!/usr/bin/env python3
"""P2: repeatable local trial over the read-only adapter; prints and stores a redacted aggregate.

Two sources, one report shape: the fixed suite below (real adapter reads over the trusted checkout)
or bundles already persisted by the adapter / Claude Read gate. Metrics are the ADR 0009 list via
H4-01b; nothing here decides, replays or grants a read, and no content or physical path is kept.
"""
import argparse
import collections
import importlib.metadata
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TRUSTED_REPOSITORY = ROOT.parent
TRUSTED_REVISION = "HEAD"
EVIDENCE_DIR = ROOT / "docs/observability/evidence"
TRIALS_DIR = ROOT / "docs/observability/trials"
MAX_OUTPUT_BYTES = 1 << 20  # same host ceiling as claude-code-read-gate.py
SUITE_VERSION = "1.0"
# Fixed, documented suite (CONTROL_PLANE.md). Changing a case bumps SUITE_VERSION.
SUITE = (
    ("happy-path", "README.md", "delivered/read_delivered"),
    ("sensitive-path", "secrets/token", "deny/sensitive_path_denied"),
    ("traversal", "docs/../README.md", "deny/invalid_referenced_contract"),
    ("binding-mismatch-pdp", "README.md", "deny/run_binding_mismatch"),  # context bound to another run: denied before the effect; its bundle has no effective_scope, so H4-01b counts it invalid
    ("binding-mismatch-pep", "README.md", "deny/task_ref_mismatch"),  # intent bound to another snapshot: admitted by the PDP, denied at the effect by the PEP
)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_REASON = re.compile(r"[a-z0-9_]{1,64}\Z")
_PUBLIC_FAILURES = {"trial_evidence_dir_unavailable", "trial_report_verification_failed", "trial_suite_expectation_failed", "trial_execution_failed", "invalid_trial_id"}

try:
    import integration.local_read_adapter as adapter_module
    from integration.evidence_trial_metrics import aggregate_trial_observations, verify_trial_report
    PACKAGE_VERSION = importlib.metadata.version("adf-control-plane")
except Exception:  # fail closed: no sys.path folklore, the package must be installed (P1)
    print("control-plane packages not importable — run: make install-dev"); raise SystemExit(1)


def _load(path): return json.loads(path.read_text(encoding="utf-8"))
def _timestamp(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def _default_trial_id(): return datetime.now(timezone.utc).strftime("trial-%Y%m%dT%H%M%SZ")


_ORIGINAL_BUILD_REQUEST = adapter_module.build_request


def _other_run(*args, **kwargs):
    request = _ORIGINAL_BUILD_REQUEST(*args, **kwargs); request["context"]["resolved_run_config_ref"]["run_id"] = f"{request['intent']['run_id']}-other"; return request


def _other_snapshot(*args, **kwargs):
    request = _ORIGINAL_BUILD_REQUEST(*args, **kwargs); request["intent"]["task_ref"] = "0" * 64; return request


# ponytail: the suite injects the two mismatches by swapping the adapter's request builder for one read; the adapter itself is untouched
_MUTATIONS = {"binding-mismatch-pdp": _other_run, "binding-mismatch-pep": _other_snapshot}


def _record(outcome, reason_code, bundle=None, latency_ms=None):
    valid_reason = isinstance(reason_code, str) and _REASON.fullmatch(reason_code)  # an unverifiable claim is tallied as an invalid deny, never echoed
    return {"outcome": "delivered" if outcome == "delivered" and valid_reason else "deny", "reason_code": reason_code if valid_reason else "evidence_bundle_invalid", "bundle": bundle, "latency_ms": latency_ms}


def run_suite(trial_id, evidence_dir):
    """Real adapter reads over the trusted checkout; content is dropped, never inspected."""
    adapter = adapter_module.LocalReadAdapter(TRUSTED_REPOSITORY, TRUSTED_REVISION, evidence_dir)
    records = []
    for case, path, _ in SUITE:
        adapter_module.build_request = _MUTATIONS.get(case, _ORIGINAL_BUILD_REQUEST)
        try: result = adapter.read(f"{trial_id}-{case}", path, MAX_OUTPUT_BYTES)
        finally: adapter_module.build_request = _ORIGINAL_BUILD_REQUEST
        result.pop("content", None)
        bundle = _load(Path(result["bundle_path"])) if result["bundle_path"] else None
        records.append(_record(result["outcome"], result["reason_code"], bundle, result["decision_latency_ms"]))
    return records


def ingest(evidence_dir):
    """Persisted bundles are evidence only: no PDP, PEP or runtime is touched here."""
    records = []
    for path in sorted(Path(evidence_dir).rglob("*.json")):
        if "_timings" in path.relative_to(evidence_dir).parent.parts:
            continue  # Separate P0-D observations are not v1 evidence bundles.
        try: bundle = _load(path)
        except Exception: records.append(_record("deny", "evidence_bundle_invalid", {"unreadable": True})); continue
        receipt = bundle.get("receipt") if isinstance(bundle, dict) else None
        if isinstance(bundle, dict) and bundle.get("decision_outcome") == "admit_read" and isinstance(receipt, dict):
            records.append(_record("delivered" if receipt.get("outcome") == "delivered" else "deny", receipt.get("reason_code"), bundle))
        else:
            records.append(_record("deny", bundle.get("reason_code") if isinstance(bundle, dict) else None, bundle if isinstance(bundle, dict) else {"unreadable": True}))
    return records


def _observation(bundle, latency_ms):
    receipt = bundle.get("receipt") if bundle.get("decision_outcome") == "admit_read" else None
    receipt = receipt if isinstance(receipt, dict) else None
    bundle_id = bundle.get("bundle_id") if isinstance(bundle.get("bundle_id"), str) and _ID.fullmatch(bundle.get("bundle_id")) else None
    if bundle_id is None: return {"invalid": True}  # H4-01b counts it in evidence_bundle_invalid_total
    return {
        "schema_version": "1.0", "observation_id": f"observation-{bundle_id[:64]}", "trial_id": f"trial-{bundle_id[:64]}", "observed_at": _timestamp(), "evidence_bundle": bundle,
        "runtime_outcome": receipt["outcome"] if receipt and isinstance(receipt.get("outcome"), str) else "not_attempted",
        "runtime_reason_code": receipt.get("reason_code") if receipt else None,
        "human_intervention_required": bundle.get("decision_outcome") == "approval_required",  # counted only; the PDP does not emit it today and this is not a HITL workflow
        "decision_latency_ms": latency_ms if isinstance(latency_ms, int) and latency_ms >= 0 else 0,
        "provenance": {"collector_version": "1.0", "kind": "local_trial_observation"},
    }


def build_report(trial_id, records, source_kind):
    schemas = adapter_module.schemas()
    schemas.update({"evidence_trial_observation": _load(ROOT / "integration/v1/schemas/evidence-trial-observation.schema.json"), "evidence_trial_report": _load(ROOT / "integration/v1/schemas/evidence-trial-report.schema.json")})
    with_bundle = [record for record in records if record["bundle"] is not None]
    latency_recorded = source_kind == "fixed_suite"  # ponytail: bundles do not carry latency, so ingested metrics.decision_latency_ms holds zero placeholders and this flag says so
    observations = [_observation(record["bundle"], record["latency_ms"]) for record in with_bundle]
    metrics = aggregate_trial_observations(observations, {"report_id": trial_id, "created_at": _timestamp(), "provenance": {"aggregator_version": "1.0", "kind": "local_evidence_trial_metrics"}}, schemas, _load(ROOT / "integration/v1/policies/evidence-metric-reason-codes-v1.json"))
    if not verify_trial_report(metrics, schemas): raise RuntimeError("trial_report_verification_failed")
    tally = collections.Counter(f"{record['outcome']}/{record['reason_code']}" for record in records)
    return {
        "schema_version": "1.0", "trial_id": trial_id, "created_at": _timestamp(),
        "source": {"kind": source_kind, "suite_version": SUITE_VERSION if source_kind == "fixed_suite" else None, "adapter_id": adapter_module.ADAPTER_ID, "adapter_version": "1.0", "package_version": PACKAGE_VERSION, "latency_recorded": latency_recorded},
        "reads_total": len(records), "bundles_total": len(with_bundle), "reason_codes": dict(sorted(tally.items())), "metrics": metrics,
    }


def persist_report(report, trials_dir):
    directory = Path(trials_dir); directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / f"{report['trial_id']}.json"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle: handle.write(json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return target


def summary(report, records, expectations_ok):
    metrics, source, latency = report["metrics"], report["source"], report["metrics"]["decision_latency_ms"]
    lines = [f"trial {report['trial_id']} · source={source['kind']} · adapter {source['adapter_id']} {source['adapter_version']} · package {source['package_version']}"]
    if source["kind"] == "fixed_suite":
        for (case, _, expected), record in zip(SUITE, records):
            actual = f"{record['outcome']}/{record['reason_code']}"
            lines.append(f"  {'✓' if actual == expected else '✗'} {case:<20} {actual}  (expected {expected})")
    lines += [
        f"decisions {metrics['decisions_total']} · admit_read {metrics['admit_read_total']} · deny {metrics['deny_total']} · bundles valid {metrics['evidence_bundle_valid_total']} invalid {metrics['evidence_bundle_invalid_total']} · reads without bundle {report['reads_total'] - report['bundles_total']}",
        f"binding_mismatch {metrics['binding_mismatch_total']} · sensitive_path_denied {metrics['sensitive_path_denied_total']} · invalid_contract {metrics['invalid_contract_total']} · human_intervention_required {metrics['human_intervention_required_total']}",
        f"decision_latency_ms: count {latency['count']} min {latency['min']} max {latency['max']} sum {latency['sum']}" if source["latency_recorded"] else "decision_latency_ms: not recorded (persisted bundles carry no latency; metrics hold zero placeholders)",
        "top reason codes: " + (", ".join(f"{code} {count}" for code, count in sorted(report["reason_codes"].items(), key=lambda item: (-item[1], item[0]))[:5]) or "none"),
    ]
    if not expectations_ok: lines.append("✗ trial_suite_expectation_failed")
    return "\n".join(lines)


def run_trial(trial_id, evidence_dir=None, trials_dir=None):
    """Return (report, records, expectations_ok); writes the redacted report when trials_dir is given."""
    if not isinstance(trial_id, str) or not _ID.fullmatch(trial_id): raise RuntimeError("invalid_trial_id")
    if evidence_dir is None:
        records, kind = run_suite(trial_id, EVIDENCE_DIR), "fixed_suite"
    else:
        if not Path(evidence_dir).is_dir(): raise RuntimeError("trial_evidence_dir_unavailable")
        records, kind = ingest(evidence_dir), "persisted_evidence"
    report = build_report(trial_id, records, kind)
    ok = kind != "fixed_suite" or all(f"{record['outcome']}/{record['reason_code']}" == expected for (_, _, expected), record in zip(SUITE, records))
    if trials_dir is not None: persist_report(report, trials_dir)
    return report, records, ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evidence-dir", help="aggregate bundles already persisted there instead of running the fixed suite")
    parser.add_argument("--trial-id", default=None)
    parser.add_argument("--no-write", action="store_true", help="print only; do not persist the JSON report")
    args = parser.parse_args(argv)
    try:
        report, records, ok = run_trial(args.trial_id or _default_trial_id(), args.evidence_dir, None if args.no_write else TRIALS_DIR)
        print(summary(report, records, ok))
        if not args.no_write: print(f"report: {TRIALS_DIR.relative_to(ROOT.parent) / (report['trial_id'] + '.json')}")
        return 0 if ok else 1
    except RuntimeError as exc:
        code = exc.args[0] if len(exc.args) == 1 else None
        print(code if code in _PUBLIC_FAILURES else "trial_execution_failed"); return 1
    except Exception:
        print("trial_execution_failed"); return 1


if __name__ == "__main__": raise SystemExit(main())
