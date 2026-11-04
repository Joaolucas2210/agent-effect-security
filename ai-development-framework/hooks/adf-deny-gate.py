#!/usr/bin/env python3
"""ADR 0028 slice 1a: deny-only PreToolUse gate for tools ADF does not mediate.

Grep/Glob (read-equivalent) are denied on `sensitive_path_policy_v1` paths; Edit/Write/MultiEdit/NotebookEdit
are denied on those plus `agent_config_policy_v1` (agent, IDE and CI configuration that later executes) and
on anything under `$ADF_HOME`. Everything else returns no decision, so the client's own permissions apply.
Paths only: the gate never opens a file, never inspects content, never persists evidence (deny without bundle).
Root comes from the host (`ADF_TRUSTED_REPOSITORY`, set by adf-read-hook.py), never from the payload.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from integration import mcp_registry  # noqa: E402
from integration.adapter_attempt import AttemptJournal  # noqa: E402
from integration.local_read_adapter import schemas as _schemas  # noqa: E402
from integration.read_gate_host import local_principal  # noqa: E402
from runtime.local_read_runtime import sensitive_path  # noqa: E402

_READ_TOOLS = {"Grep": "path", "Glob": "path"}
_WRITE_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
_NETWORK_TOOLS = {"WebFetch"}
_NETWORK_BASH = re.compile(r"(?<![\w./-])(curl|wget)(?![\w-])")
# ADR 0028 1c: a run that tried to reach a sensitive path may not open a network channel afterwards (trifecta leg 3).
_TAINTING = {"sensitive_path_denied", "sensitive_argument_rejected", "invalid_scope", "uncovered_read_denied_sensitive", "uncovered_write_denied_sensitive"}
_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SENSITIVE = json.loads((ROOT / "runtime/v1/policies/sensitive-path-policy-v1.json").read_text(encoding="utf-8"))
_AGENT_CONFIG = json.loads((ROOT / "runtime/v1/policies/agent-config-policy-v1.json").read_text(encoding="utf-8"))


def _decision(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": f"adf: {reason}"}}


def _under(path, base):
    return path == base or path.startswith(base.rstrip("/") + "/")


def _relatives(target, root):
    """Lexical and real relative paths of `target` under `root`; a path outside yields nothing."""
    absolute = target if target.startswith("/") else os.path.join(root, target)
    out = set()
    for candidate, base in ((os.path.normpath(absolute), root), (os.path.realpath(absolute), os.path.realpath(root))):
        if _under(candidate, base) and candidate != base:
            out.add(os.path.relpath(candidate, base))
    return out


def _agent_config(rel):
    return any(part in _AGENT_CONFIG["deny_components"] for part in rel.split("/")) or any(_under(rel, deny) for deny in _AGENT_CONFIG["deny_paths"])


def _mcp(tool):
    """ADR 0031 slice 1: names only, against the host-pinned registry; unconfigured -> no decision."""
    try:
        config = mcp_registry.configured()
        if config is None:
            return None
        reason = mcp_registry.decide(tool, mcp_registry.load(*config))
    except mcp_registry.RegistryInvalid:
        return _decision("mcp_registry_invalid")
    return _decision(reason) if reason else None


def network_shaped(payload):
    """True for WebFetch and for Bash whose command names curl/wget; the dispatcher routes those here first."""
    tool = payload.get("tool_name") if isinstance(payload, dict) else None
    command = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) and isinstance(payload.get("tool_input"), dict) else None
    return tool in _NETWORK_TOOLS or (tool == "Bash" and isinstance(command, str) and _NETWORK_BASH.search(command) is not None)


def _run_tainted(evidence_dir, run_id):
    """Journal-only, path-free: did this run already attempt a sensitive path? Any unreadable journal counts as tainted."""
    project_dir = Path(evidence_dir).parent  # evidence/<project>/<day>: a session may cross midnight
    try:
        for path in project_dir.rglob("_attempts/*.jsonl"):
            try:
                events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            except (OSError, ValueError):
                return True
            for event in events:
                if isinstance(event, dict) and event.get("phase") == "completed" and event.get("run_id") == run_id and (event.get("payload") or {}).get("reason_code") in _TAINTING:
                    return True
    except OSError:
        return True
    return False


def journal_deny(payload, reason):
    """Two-event attempt journal for a deny that never reached the adapter; failure to journal never turns a deny into an allow."""
    evidence_dir, run_id = os.environ.get("ADF_EVIDENCE_DIR"), payload.get("session_id") if isinstance(payload, dict) else None
    if not evidence_dir or not isinstance(run_id, str) or not _RUN.fullmatch(run_id):
        return
    principal = local_principal(payload, "claude") if isinstance(payload, dict) else None
    try:
        journal = AttemptJournal(evidence_dir, run_id, _schemas()["adapter_attempt_event"], principal, adapter_id="deny-only-gate")
        try:
            journal.finish({"outcome": "deny", "reason_code": reason, "bundle_id": None})
        finally:
            journal.close()
    except Exception:
        pass


def gate(payload):
    """Path-only mapping to `deny` or None; a malformed payload in an enabled project denies. Every deny is journaled."""
    decision = _decide(payload)
    if decision is not None:
        journal_deny(payload, decision["hookSpecificOutput"]["permissionDecisionReason"].removeprefix("adf: "))
    return decision


def _decide(payload):
    tool = payload.get("tool_name") if isinstance(payload, dict) else None
    if network_shaped(payload):
        evidence_dir, run_id = os.environ.get("ADF_EVIDENCE_DIR"), payload.get("session_id")
        if not evidence_dir or not isinstance(run_id, str):
            return _decision("host_configuration_invalid")
        return _decision("uncovered_network_denied_after_sensitive_read") if _run_tainted(evidence_dir, run_id) else None
    if isinstance(tool, str) and tool.startswith("mcp__"):
        return _mcp(tool)
    key = _READ_TOOLS.get(tool) or _WRITE_TOOLS.get(tool)
    if key is None:
        return _decision("unsupported_tool")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return _decision("unexpected_tool_input")
    target = tool_input.get(key)
    if target is None and tool in _READ_TOOLS:
        return None  # ponytail: Grep/Glob over the whole root stay a documented residual (ADR 0028)
    if not isinstance(target, str) or not target or "\x00" in target:
        return _decision("unexpected_tool_input")
    root = os.environ.get("ADF_TRUSTED_REPOSITORY")
    if not root or not root.startswith("/"):
        return _decision("host_configuration_invalid")
    write = tool in _WRITE_TOOLS
    adf_home = os.environ.get("ADF_HOME") or str(Path.home() / ".adf")
    absolute = target if target.startswith("/") else os.path.join(root, target)
    if write and any(_under(os.path.normpath(absolute), base) or _under(os.path.realpath(absolute), os.path.realpath(base)) for base in (adf_home,)):
        return _decision("uncovered_write_denied_agent_config")
    rels = _relatives(target, root)
    if any(sensitive_path(rel, _SENSITIVE) for rel in rels):
        return _decision("uncovered_write_denied_sensitive" if write else "uncovered_read_denied_sensitive")
    if write and any(_agent_config(rel) for rel in rels):
        return _decision("uncovered_write_denied_agent_config")
    return None


def main():
    try:
        decision = gate(json.loads(sys.stdin.read()))
    except Exception:
        decision = _decision("adapter_failed")
    if decision is not None:
        print(json.dumps(decision, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
