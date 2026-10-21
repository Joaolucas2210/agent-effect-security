"""Host-owned settings shared by native Read and Bash-read hooks."""
import os
import re
import time
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPOSITORY = ROOT.parent
DEFAULT_EVIDENCE_DIR = ROOT / "docs/observability/evidence"
DEFAULT_MAX_OUTPUT_BYTES = 1 << 20
_AGENT_TYPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
LOCAL_PRINCIPAL_TTL_SECONDS = 3600  # ADR 0023: outlives any hook process; the PEP still checks it


def local_principal(payload, edge):
    """ADR 0023: a CallerPrincipal derived from the host harness, never from tool_input.

    Claude Code puts `agent_type` in the hook payload inside a subagent and omits it on the main thread
    (verified 2026-10-21). sub = `<edge>:<agent_type or main>`; scopes are the single local read scope.
    Returns None when the field is malformed: the caller denies, because the host harness is the trust root."""
    agent_type = payload.get("agent_type", "main")
    if not isinstance(agent_type, str) or not _AGENT_TYPE.fullmatch(agent_type):
        return None
    return {"schema_version": "1.0", "sub": f"{edge}:{agent_type}", "scopes": ["workspace:read"], "act": [], "token_aud": "local-host", "authn_method": "host_harness", "expires_at": int(time.time()) + LOCAL_PRINCIPAL_TTL_SECONDS}


def relative_path(file_path, root):
    """Lexical only: `..` survives and is denied downstream by the PDP."""
    if not isinstance(file_path, str) or not file_path.startswith("/"): return None
    candidate = PurePosixPath(file_path)
    return str(candidate.relative_to(PurePosixPath(root))) if candidate.is_relative_to(PurePosixPath(root)) else None


def host_settings():
    """Resolve host-owned settings; the ADF layout alone has built-in defaults."""
    configured_root = os.environ.get("ADF_TRUSTED_REPOSITORY")
    project_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if configured_root is None and project_root is not None and Path(project_root).resolve() != DEFAULT_REPOSITORY:
        return None
    root = Path(configured_root) if configured_root is not None else DEFAULT_REPOSITORY
    evidence_value = os.environ.get("ADF_EVIDENCE_DIR")
    evidence = Path(evidence_value) if evidence_value is not None else DEFAULT_EVIDENCE_DIR if configured_root is None else None
    revision = os.environ.get("ADF_TRUSTED_REVISION", "HEAD")
    budget_value = os.environ.get("ADF_MAX_OUTPUT_BYTES", str(DEFAULT_MAX_OUTPUT_BYTES))
    if not root.is_absolute() or not root.is_dir() or evidence is None or not evidence.is_absolute() or (evidence.exists() and not evidence.is_dir()):
        return None
    if not revision or revision.startswith("-") or "\x00" in revision or not budget_value.isascii() or not budget_value.isdecimal() or int(budget_value) < 1:
        return None
    return root.resolve(), revision, evidence.resolve(), int(budget_value)


def host_policy_settings():
    """Both absent selects the demo; partial/invalid configuration is denied by the adapter."""
    return {"host_policy_path": os.environ.get("ADF_READ_POLICY_FILE"), "host_policy_sha256": os.environ.get("ADF_READ_POLICY_SHA256")}


def read_adapter(adapter, run_id, path, budget, evidence_dir, principal=None):
    """The host opts into diagnostic timings; agent input never selects this setting."""
    if os.environ.get("ADF_CAPTURE_TIMINGS") != "1":
        return adapter.read(run_id, path, budget, principal=principal)
    from integration.attempt_timing import read_observed
    return read_observed(adapter, run_id, path, budget, evidence_dir, principal)
