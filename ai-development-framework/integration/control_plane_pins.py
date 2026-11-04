"""ADR 0027: host-pinned manifest of the control plane's own code, host files and hook registration.

`adf doctor --pin` (a human) writes `$ADF_HOME/pins.json` (0400). Every gate invocation recomputes the same
snapshot first; any divergence is `control_plane_tampered` and the call is denied before any gate runs.
No manifest = not pinned = unchanged behaviour (`adf doctor` exits 3, never green). What it does not do: resist
root or the user, or prove that this very checker was not replaced along with the manifest (ADR 0030's key and
ADR 0028's `~/.adf` write deny are the companions).
"""
import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

_CODE = ("hooks/adf-read-hook.py", "hooks/adf-deny-gate.py", "hooks/claude-code-read-gate.py", "hooks/codex-bash-read-gate.py", "hooks/adf-projects.py")
_CODE_GLOBS = ("integration/*.py", "tools/*.py", "runtime/*.py", "runtime/v1/policies/*.json", "policy-packs/*/build.py")
_HOST_ENV = ("ADF_READ_POLICY_FILE", "ADF_MCP_REGISTRY_FILE", "ADF_A2A_JWKS_FILE", "ADF_EVIDENCE_KEY_FILE")


def _sha256(path):
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return None  # missing is a value too: a file that appears or disappears is a divergence


_ASSIGN = re.compile(r"(?:^|[\s;])(?:export\s+)?(ADF_[A-Z0-9_]+)=([^\s;]+)")


def registered_env(home):
    """Host env files as the registered hook command exports them (`export ADF_X=/path; ...`), so a terminal
    without those variables sees the same snapshot the hook sees. The shell value, when set, wins."""
    found = {}
    try:
        settings = json.loads((Path(home) / ".claude/settings.json").read_text(encoding="utf-8"))
        for entry in settings["hooks"]["PreToolUse"]:
            for hook in entry.get("hooks", []):
                command = str(hook.get("command", ""))
                if "adf" in command and " hook" in command:
                    for name, value in _ASSIGN.findall(command):
                        found.setdefault(name, value.strip("\"'"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return found


def host_env(name, home):
    return os.environ.get(name) or registered_env(home).get(name)


def describe(labels, limit=5):
    """Short, path-free summary for a deny reason: first labels plus a count."""
    labels = list(labels)
    head = ", ".join(labels[:limit])
    return head + (f" +{len(labels) - limit} more" if len(labels) > limit else "")


def clone_line(root):
    """`branch @ short-sha` of the clone the checker runs from; `na` when git cannot say (never a path)."""
    try:
        branch = subprocess.run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
        sha = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
        return f"{branch} @ {sha}" if branch and sha else "na"
    except (OSError, subprocess.SubprocessError):
        return "na"


def _registration(home):
    """Matchers under which the ADF hook is registered in the user's Claude settings; sorted, exact strings."""
    try:
        settings = json.loads((Path(home) / ".claude/settings.json").read_text(encoding="utf-8"))
        entries = settings["hooks"]["PreToolUse"]
        return sorted(str(entry["matcher"]) for entry in entries if any("adf" in str(hook.get("command", "")) and " hook" in str(hook.get("command", "")) for hook in entry.get("hooks", [])))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


def snapshot(root, adf_home):
    root, adf_home = Path(root), Path(adf_home)
    files = {label: _sha256(root / label) for label in _CODE}
    for pattern in _CODE_GLOBS:
        for path in sorted(root.glob(pattern)):
            files[str(path.relative_to(root))] = _sha256(path)
    files["host:enabled-projects"] = _sha256(adf_home / "enabled-projects")
    home = Path(os.environ.get("HOME") or Path.home())
    for name in _HOST_ENV:
        value = host_env(name, home)
        if value:
            files[f"host:{name}"] = _sha256(value)
    return {"schema_version": "1.0", "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "files": files, "registration": _registration(home)}


def write_manifest(path, snap):
    """0400, replaced atomically; only a human runs this (`adf doctor --pin`)."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(snap, sort_keys=True, separators=(",", ":")))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def read_manifest(path):
    """-> manifest dict, or None when not pinned. Any unusable manifest is a divergence, never 'not pinned'."""
    path = Path(path)
    try:
        info = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return None
    try:
        if not stat.S_ISREG(info.st_mode) or (info.st_mode & 0o777) != 0o400:
            raise ValueError("manifest_mode")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != "1.0" or not isinstance(data.get("files"), dict) or not isinstance(data.get("registration"), list):
            raise ValueError("manifest_shape")
        return data
    except (OSError, ValueError) as exc:
        return {"invalid": str(exc)}


def divergences(manifest, current):
    """Labels that differ, 'manifest' when the manifest itself is unusable; [] means intact."""
    if "invalid" in manifest:
        return ["manifest"]
    labels = set(manifest["files"]) | set(current["files"])
    out = sorted(label for label in labels if manifest["files"].get(label) != current["files"].get(label))
    if manifest["registration"] != current["registration"]:
        out.append("registration")
    return out


def check(root, adf_home):
    """-> None (not pinned) or the list of divergences ([] = intact)."""
    manifest = read_manifest(Path(adf_home) / "pins.json")
    if manifest is None:
        return None
    return divergences(manifest, snapshot(root, adf_home))
