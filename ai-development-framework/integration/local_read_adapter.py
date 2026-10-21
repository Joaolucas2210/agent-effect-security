"""Read-only reference adapter: one harness read intent -> H2-02 -> H3-01 -> H4-01 bundle.

It composes existing layers and never changes their semantics. Trusted repository, revision and
evidence directory come from the host; the agent supplies only a relative path.
"""
import copy
import json
import os
import re
import time
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from jsonschema import Draft7Validator

from integration.adapter_attempt import AttemptJournal
from integration.attempt_timing import call_stage
from integration.local_evidence_bundle import compose, digest, verify_offline
from runtime.local_read_runtime import LocalReadRuntime
from runtime.pep import PolicyEnforcementPoint
from runtime.workspace_manager import WORKSPACE_FAILURE_CODES, WorkspaceManager
from tools.pdp import decide


ROOT = Path(__file__).resolve().parent.parent
ADAPTER_ID = "local-read-adapter"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_TAINT = {"classification": "untrusted_workspace_file", "cannot_authorize": True}
_SCHEMA_FILES = {
    "tool_profile": "tools/v1/schemas/tool-profile.schema.json", "tool_call_intent": "tools/v1/schemas/tool-call-intent.schema.json", "policy_bundle": "tools/v1/schemas/policy-bundle.schema.json", "policy_context": "tools/v1/schemas/policy-context.schema.json", "admission_decision": "tools/v1/schemas/admission-decision.schema.json", "list_files_input": "tools/v1/schemas/list-files-input.schema.json",
    "runtime_workspace_descriptor": "runtime/v1/schemas/runtime-workspace-descriptor.schema.json", "runtime_audit_receipt": "runtime/v1/schemas/runtime-audit-receipt.schema.json", "read_result": "runtime/v1/schemas/read-result.schema.json",
    "adapter_request": "integration/v1/schemas/adapter-request.schema.json", "evidence_bundle": "integration/v1/schemas/evidence-bundle.schema.json",
    "adapter_attempt_event": "integration/v1/schemas/adapter-attempt-event.schema.json",
    "caller_principal": "integration/v1/schemas/caller-principal.schema.json", "a2a_evidence_record": "integration/v1/schemas/a2a-evidence-record.schema.json",
}


def _load(relative): return json.loads((ROOT / relative).read_text(encoding="utf-8"))
def _timestamp(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def _rehash(value, field): value[field] = digest({key: item for key, item in value.items() if key != field})
def schemas(): return {name: _load(path) for name, path in _SCHEMA_FILES.items()}


def load_host_policy(path, fingerprint, contract_schemas):
    """Load and pin host-owned artifacts once; never repair hashes or expand grants."""
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint) or path is None or not Path(path).is_absolute():
        raise ValueError("host_policy_invalid")
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != {"schema_version", "profiles", "policy", "context"} or config["schema_version"] != "1.0" or digest(config) != fingerprint:
        raise ValueError("host_policy_invalid")
    if not isinstance(config["profiles"], list) or len(config["profiles"]) != 1:
        raise ValueError("host_policy_invalid")
    profile, policy = config["profiles"][0], config["policy"]
    for value, name in ((profile, "tool_profile"), (policy, "policy_bundle"), (config["context"], "policy_context")):
        Draft7Validator(contract_schemas[name]).validate(value)
    if len(profile["operations"]) != 1 or any(value[field] != digest({key: item for key, item in value.items() if key != field}) for value, field in ((profile, "profile_sha256"), (policy, "policy_sha256"))):
        raise ValueError("host_policy_invalid")
    return config


def build_request(descriptor, run_id, path, max_output_bytes, created_at=None, host_policy=None):
    """Compose an intent; only the explicit reference demo synthesizes grants from its path."""
    examples = "tools/v1/examples"
    intent = _load(f"{examples}/tool-call-intent/valid/read-worktree.json")
    scope = {"kind": "filesystem", "path": path}
    if host_policy is None:
        profile, policy = _load(f"{examples}/tool-profile/valid/read-worktree.json"), _load(f"{examples}/policy-bundle/valid/read-worktree.json")
        context = _load(f"{examples}/policy-context/valid/read-worktree.json")
        profile["operations"][0].update(supported_scopes=[scope], max_risk={"level": "low", "max_output_bytes": max_output_bytes}); _rehash(profile, "profile_sha256")
        policy["rules"][0].update(profile_sha256=profile["profile_sha256"], allowed_scopes=[scope], max_output_bytes=max_output_bytes); _rehash(policy, "policy_sha256")
        for name in ("organizational_constraints", "repository_constraints", "mode_constraints"): context[name].update(allowed_scopes=[scope], max_output_bytes=max_output_bytes)
        context["resolved_run_config_ref"]["run_id"] = run_id; context["policy_ref"] = {"policy_id": policy["policy_id"], "policy_sha256": policy["policy_sha256"]}
    else:
        pinned = copy.deepcopy(host_policy)
        profile, policy, context = pinned["profiles"][0], pinned["policy"], pinned["context"]
    intent.update(intent_id=f"intent-{run_id}", run_id=run_id, task_ref=descriptor["snapshot_digest"], resource_scope=scope, arguments={"path": path}, requested_budget={"max_output_bytes": max_output_bytes}, policy_context_ref=copy.deepcopy(context["policy_ref"]))
    intent["tool_ref"] = {"tool_id": profile["tool_id"], "profile_sha256": profile["profile_sha256"]}
    intent["operation_id"] = profile["operations"][0]["operation_id"]
    return {"schema_version": "1.0", "adapter_id": ADAPTER_ID, "created_at": created_at or _timestamp(), "intent": intent, "profiles": [profile], "policy": policy, "context": context, "workspace": descriptor, "provenance": {"adapter_version": "1.0", "kind": "local_structured_adapter"}}


def persist_bundle(bundle, evidence_dir, run_id):
    """Write the redacted bundle under evidence_dir/<run_id>/, owner-only, never overwriting."""
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = evidence_dir / run_id
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / f"{bundle['bundle_id']}.json"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(bundle, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return target


def _result(outcome, reason_code, bundle=None, bundle_path=None, content=None, latency_ms=0):
    result = {"adapter_id": ADAPTER_ID, "outcome": outcome, "reason_code": reason_code, "taint": dict(_TAINT), "bundle_id": bundle["bundle_id"] if bundle else None, "bundle_path": str(bundle_path) if bundle_path else None, "decision_latency_ms": latency_ms}
    if content is not None: result["content"] = content
    return result


class _CapturingPEP:
    """Keeps the tainted content out of the bundle while still handing it to the harness once."""
    def __init__(self, pep, principal=None): self._pep, self.content, self._principal = pep, None, principal
    def enforce_read(self, *args):
        result, receipt = self._pep.enforce_read(*args) if self._principal is None else self._pep.enforce_read(*args, principal=self._principal)
        if result.get("outcome") == "delivered": self.content = result["content"]
        return result, receipt


class LocalReadAdapter:
    """Host-configured; agents never supply repository, revision, root, or evidence location."""
    def __init__(self, trusted_repository, trusted_revision, evidence_dir, workspace_parent=None, *, host_policy_path=None, host_policy_sha256=None):
        self._repository, self._revision, self._evidence, self._parent = trusted_repository, trusted_revision, Path(evidence_dir), workspace_parent
        self._schemas = schemas()
        self._sensitive = _load("runtime/v1/policies/sensitive-path-policy-v1.json")
        self._host_policy, self._host_policy_invalid = None, False
        if host_policy_path is not None or host_policy_sha256 is not None:
            try: self._host_policy = load_host_policy(host_policy_path, host_policy_sha256, self._schemas)
            except Exception: self._host_policy_invalid = True

    def read(self, run_id, path, max_output_bytes, *, timing=None, principal=None):
        """Return a closed, tainted result; content is present only when the PEP delivered it."""
        safe_run_id = run_id if isinstance(run_id, str) and _ID.fullmatch(run_id) else None
        try: journal = call_stage(timing, "persistence", AttemptJournal, self._evidence, safe_run_id, self._schemas["adapter_attempt_event"], principal)
        except Exception: return _result("deny", "attempt_evidence_failed")
        if timing is not None:
            timing.start = dict(journal._start)
        try:
            outcome = self._read(run_id, path, max_output_bytes, journal, timing, principal)
            call_stage(timing, "persistence", journal.finish, outcome)
            return outcome
        except Exception:
            return _result("deny", "attempt_evidence_failed")
        finally:
            journal.close()

    def _read(self, run_id, path, max_output_bytes, journal, timing=None, principal=None):
        if not isinstance(run_id, str) or not _ID.fullmatch(run_id): return _result("deny", "invalid_run_id")
        if not isinstance(path, str) or not path or path.startswith("/") or "\x00" in path: return _result("deny", "invalid_scope")
        if type(max_output_bytes) is not int or max_output_bytes < 0: return _result("deny", "invalid_budget")
        if self._host_policy_invalid: return _result("deny", "host_policy_invalid")
        try:
            manager = WorkspaceManager(self._repository, self._revision, self._parent); descriptor = call_stage(timing, "prepare", manager.prepare, run_id)
        except RuntimeError as exc:
            return _result("deny", exc.args[0] if exc.args and exc.args[0] in WORKSPACE_FAILURE_CODES else "workspace_worktree_prepare_failed")
        except Exception:
            return _result("deny", "workspace_worktree_prepare_failed")
        try:
            try: outcome = self._attempt(manager, descriptor, run_id, path, max_output_bytes, timing, principal)
            except Exception: outcome = _result("deny", "adapter_failed")
        finally:
            try: cleaned = call_stage(timing, "cleanup", manager.cleanup, descriptor["workspace_id"])
            except Exception: cleaned = False
            journal.cleanup_outcome = "succeeded" if cleaned else "failed"
        if not cleaned:  # ADR 0008: failed cleanup is never a successful run, so no content leaves
            outcome.pop("content", None); outcome.update(outcome="deny", reason_code="workspace_worktree_cleanup_failed")
        return outcome

    def _attempt(self, manager, descriptor, run_id, path, max_output_bytes, timing=None, principal=None):
        started = time.monotonic()
        runtime = LocalReadRuntime(self._sensitive)
        if timing is not None:
            runtime.read = partial(timing.call, "read", runtime.read)
        pep = _CapturingPEP(PolicyEnforcementPoint(manager, runtime), principal)
        decide_fn = None if principal is None else partial(decide, principal=principal)  # None keeps the pre-A2A-3 path byte-identical
        try: bundle = compose(build_request(descriptor, run_id, path, max_output_bytes, host_policy=self._host_policy), self._schemas, pep, decide_fn=partial(timing.call, "decision", decide_fn or decide) if timing is not None else decide_fn)
        except ValueError as exc: return _result("deny", exc.args[0] if exc.args else "invalid_adapter_request")
        latency = int((time.monotonic() - started) * 1000)
        bundle_path = call_stage(timing, "persistence", persist_bundle, bundle, self._evidence, run_id)  # P2 also counts invalid bundles
        if bundle["decision_outcome"] != "admit_read": return _result("deny", bundle["reason_code"], bundle, bundle_path, latency_ms=latency)
        if not verify_offline(bundle, self._schemas): return _result("deny", "evidence_bundle_invalid", bundle, bundle_path, latency_ms=latency)
        receipt = bundle["receipt"]
        if receipt["outcome"] != "delivered" or pep.content is None: return _result("deny", receipt["reason_code"], bundle, bundle_path, latency_ms=latency)
        return _result("delivered", receipt["reason_code"], bundle, bundle_path, pep.content, latency)
