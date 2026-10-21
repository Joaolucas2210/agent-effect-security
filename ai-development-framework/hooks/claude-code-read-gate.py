#!/usr/bin/env python3
"""Claude Code PreToolUse gate for `Read`: control-plane decision + evidence before the native read.

The hook allows or denies the native Read tool; it never injects content. Repository, revision,
budget and evidence location come from the host environment, not from the agent payload.
"""
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
_READ_KEYS = {"file_path", "offset", "limit", "pages"}

sys.path.insert(0, str(ROOT))
from integration.local_read_adapter import LocalReadAdapter  # noqa: E402
from integration.read_gate_host import host_settings as _host_settings, host_policy_settings, local_principal, relative_path, read_adapter  # noqa: E402
from integration.otel_export import emit_local_read  # noqa: E402


def _decision(permission, reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": permission, "permissionDecisionReason": f"adf: {reason}"}}


def gate(payload):
    """Pure mapping from a hook payload to a permission decision; every failure denies."""
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "PreToolUse" or payload.get("tool_name") != "Read": return _decision("deny", "unsupported_tool")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict) or "file_path" not in tool_input or set(tool_input) - _READ_KEYS: return _decision("deny", "unexpected_tool_input")
    settings = _host_settings()
    if settings is None: return _decision("deny", "host_configuration_invalid")
    repository, revision, evidence_dir, max_output_bytes = settings
    path = relative_path(tool_input["file_path"], repository)
    if path is None: return _decision("deny", "path_outside_trusted_root")
    principal = local_principal(payload, "claude")  # ADR 0023: host-derived; a malformed agent_type is a deny
    if principal is None: return _decision("deny", "invalid_principal")
    start_ns = time.time_ns()
    result = read_adapter(LocalReadAdapter(repository, revision, evidence_dir, **host_policy_settings()), payload.get("session_id"), path, max_output_bytes, evidence_dir, principal)
    emit_local_read("claude_read", result, start_ns, hook=True, agent_type=principal["sub"].split(":", 1)[1])  # ADR 0021: view only, after the decision
    reason = f"{result['outcome']}/{result['reason_code']}" + (f" bundle={result['bundle_id']}" if result["bundle_id"] else "")
    return _decision("allow" if result["outcome"] == "delivered" else "deny", reason)


def main():
    try: decision = gate(json.loads(sys.stdin.read()))
    except Exception: decision = _decision("deny", "adapter_failed")
    print(json.dumps(decision, separators=(",", ":"), sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
