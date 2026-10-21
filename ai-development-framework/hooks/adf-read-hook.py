#!/usr/bin/env python3
"""REQ-MP-01: one global PreToolUse hook for many projects (Claude `Read`, Codex `Bash` cat).

Projects opt in through a host-owned list (`$ADF_HOME/enabled-projects`, default `~/.adf`), one
canonical absolute path per line. Anything else passes through with no decision, so the agent's normal
permissions apply. An enabled project is gated by this clone's edge gate for the tool (`Read` ->
claude-code-read-gate.py, `Bash` -> codex-bash-read-gate.py, which only decides a single allowlisted
`cat PATH`), with the trusted root derived from the host (CLAUDE_PROJECT_DIR, else the session `cwd` the
host puts in the payload) and evidence under `$ADF_HOME/evidence/<project-id>/<YYYY-MM-DD>/`, outside
the client repo. Enabled + any failure = deny.
Residual: the agent can edit the list through Bash; the list only keeps the switch out of the workspace.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_GATES = {"Read": "hooks/claude-code-read-gate.py", "Bash": "hooks/codex-bash-read-gate.py"}


def adf_home(): return Path(os.environ.get("ADF_HOME") or Path.home() / ".adf")


def _canonical(entry):
    return entry.startswith("/") and "\x00" not in entry and ".." not in entry.split("/") and os.path.normpath(entry) == entry


def enabled_projects():
    """Unreadable or missing list = nothing enabled (never brick the machine). Bad lines never enable."""
    try:
        lines = (adf_home() / "enabled-projects").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return frozenset()
    return frozenset(os.path.realpath(line) for line in lines if _canonical(line))


def _git_root(directory):
    try:
        out = subprocess.run(["git", "-C", directory, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return os.path.realpath(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def project_id(root):
    root = os.path.realpath(root)
    return f"{Path(root).name}-{hashlib.sha256(root.encode()).hexdigest()[:8]}"


def _deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": f"adf: {reason}"}}


def _gate(payload):
    """Import lazily: a broken ADF install must not affect projects that are not enabled."""
    sys.path.insert(0, str(ROOT))
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("adf_edge_gate", ROOT / _GATES[payload["tool_name"]])
    gate = module_from_spec(spec); spec.loader.exec_module(gate)
    return gate.gate(payload)


def _project_dir(payload):
    """Claude exports CLAUDE_PROJECT_DIR; Codex only reports the session cwd inside the payload. Both are set by the host."""
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    return os.environ.get("CLAUDE_PROJECT_DIR") or (cwd if isinstance(cwd, str) and cwd.startswith("/") else None)


def decide(raw):
    """-> PreToolUse decision dict, {} for no-block (Codex contract), or None for no decision (pass-through)."""
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = None
    project = _project_dir(payload)
    if not project:
        return None
    enabled = enabled_projects()
    directory = os.path.realpath(project)
    root = _git_root(directory)
    if not enabled or (directory not in enabled and root not in enabled):
        return None
    try:
        if root is None:
            return _deny("project_not_git")
        if not isinstance(payload, dict) or payload.get("tool_name") not in _GATES:
            return _deny("unsupported_tool")
        os.environ["ADF_TRUSTED_REPOSITORY"] = root  # host-derived; a stale export for another repo is overridden
        os.environ.setdefault("ADF_TRUSTED_REVISION", "HEAD")
        os.environ.setdefault("ADF_MAX_OUTPUT_BYTES", str(1 << 20))
        evidence = adf_home() / "evidence"
        evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.environ.setdefault("ADF_EVIDENCE_DIR", str(evidence / project_id(root) / datetime.now(timezone.utc).strftime("%Y-%m-%d")))
        return _gate(payload)
    except Exception:  # enabled project: fail closed
        return _deny("adapter_failed")


def main():
    try:
        decision = decide(sys.stdin.read())
    except Exception:  # only reachable before a project is known to be enabled
        decision = None
    if decision is not None:
        print(json.dumps(decision, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
