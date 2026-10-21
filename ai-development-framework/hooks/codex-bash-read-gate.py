#!/usr/bin/env python3
"""Codex PreToolUse gate for a single-file `cat` Bash command."""
import json
import os
import re
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from integration.local_read_adapter import LocalReadAdapter  # noqa: E402
from integration.read_gate_host import host_settings, host_policy_settings, local_principal, relative_path, read_adapter  # noqa: E402
from integration.otel_export import emit_local_read  # noqa: E402


_CAT = re.compile(r"[ \t]*cat[ \t]+(?:--[ \t]+)?([A-Za-z0-9_./-]+)[ \t]*\Z")
_CAT_PREFIX = re.compile(r"(?:\A|[;&|()\n])[ \t]*(?:/(?:usr/)?bin/|(?:env|command|sudo)[ \t]+)?cat(?=$|[^A-Za-z0-9_])")
_INPUT_KEYS = {"command", "workdir", "description", "yield_time_ms", "max_output_tokens", "tty", "sandbox_permissions", "justification", "prefix_rule"}


def parse_read_equivalent_bash(command):
    """Return the one path, None for other commands, or reject malformed cat."""
    if not isinstance(command, str): raise ValueError("unexpected_tool_input")
    match = _CAT.fullmatch(command)
    if match and not match[1].startswith("-"): return match[1]
    if _CAT_PREFIX.search(command): raise ValueError("unsafe_read_command")
    return None


def _decision(permission, reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": permission, "permissionDecisionReason": f"adf: {reason}"}}


def gate(payload):
    if not isinstance(payload, dict): return _decision("deny", "invalid_hook_payload")
    if payload.get("hook_event_name") != "PreToolUse" or payload.get("tool_name") != "Bash": return {}
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict): return _decision("deny", "unexpected_tool_input")
    try: path = parse_read_equivalent_bash(tool_input.get("command"))
    except ValueError as exc: return _decision("deny", str(exc))
    if path is None: return {}
    if set(tool_input) - _INPUT_KEYS: return _decision("deny", "unexpected_tool_input")
    workdir = tool_input.get("workdir", str(Path.cwd()))
    if not isinstance(workdir, str) or not Path(workdir).is_absolute(): return _decision("deny", "unexpected_tool_input")
    if not os.environ.get("ADF_TRUSTED_REPOSITORY") or not os.environ.get("ADF_EVIDENCE_DIR"): return _decision("deny", "host_configuration_invalid")
    settings = host_settings()
    if settings is None: return _decision("deny", "host_configuration_invalid")
    repository, revision, evidence_dir, max_output_bytes = settings
    absolute_path = path if path.startswith("/") else str(Path(workdir) / path)
    relative = relative_path(absolute_path, repository)
    if relative is None: return _decision("deny", "path_outside_trusted_root")
    principal = local_principal(payload, "codex")  # ADR 0023: host-derived; a malformed agent_type is a deny
    if principal is None: return _decision("deny", "invalid_principal")
    start_ns = time.time_ns()
    result = read_adapter(LocalReadAdapter(repository, revision, evidence_dir, **host_policy_settings()), payload.get("session_id"), relative, max_output_bytes, evidence_dir, principal)
    emit_local_read("codex_bash", result, start_ns, hook=True, agent_type=principal["sub"].split(":", 1)[1])  # ADR 0021: view only, after the decision
    reason = f"{result['outcome']}/{result['reason_code']}" + (f" bundle={result['bundle_id']}" if result["bundle_id"] else "")
    return {} if result["outcome"] == "delivered" else _decision("deny", reason)


def main():
    try: decision = gate(json.loads(sys.stdin.read()))
    except Exception: decision = _decision("deny", "adapter_failed")
    print(json.dumps(decision, separators=(",", ":"), sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
