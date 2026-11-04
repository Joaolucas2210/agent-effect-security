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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from runtime.local_read_runtime import sensitive_path  # noqa: E402

_READ_TOOLS = {"Grep": "path", "Glob": "path"}
_WRITE_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
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


def gate(payload):
    """Path-only mapping to `deny` or None; a malformed payload in an enabled project denies."""
    tool = payload.get("tool_name") if isinstance(payload, dict) else None
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
