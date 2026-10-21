#!/usr/bin/env python3
"""REQ-MP-02: operate the host project list behind adf-read-hook.py without hand-editing it.

  list                 one line per entry of $ADF_HOME/enabled-projects and how the hook will treat it
  enable <abs-path>    append the canonical absolute path (git root recommended)
  disable <abs-path>   remove it
  reasons [--policy F] reason_code counts per project from $ADF_HOME/evidence/** (counts only, no bodies):
                       bundles, journal attempts (contract denies without bundle included) and, per principal,
                       attempts/delivered/denied/paths_read; with --policy, granted vs unused paths (ADR 0024)

Same rules as the hook: absolute, normalized, no `..`; symlinks resolve to the real path. Residual: an
agent can run this (or edit the file) through Bash; the list keeps the switch out of the workspace, no more.
"""
import importlib.util
import json
import os
import sys
from collections import Counter
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("adf_read_hook", Path(__file__).resolve().with_name("adf-read-hook.py"))
hook = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(hook)


def _file(): return hook.adf_home() / "enabled-projects"


def _lines():
    try: return [line for line in _file().read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError): return []


def _write(lines):
    """Owner-only file, replaced atomically; non-canonical lines are kept (listed as ignored), never dropped silently."""
    _file().parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = _file().with_name("enabled-projects.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle: handle.write("".join(f"{line}\n" for line in lines))
    os.replace(tmp, _file())


def _require(path):
    if not path: raise SystemExit("adf: no project given. Usage: make project-enable PROJECT=/abs/git/root (or project-disable)")


def _canonical_arg(path):
    _require(path)
    if not hook._canonical(path): raise SystemExit(f"adf: rejected {path!r}: use an absolute normalized path (no '..', '//' or trailing '/')")
    real = os.path.realpath(path)
    if not os.path.isdir(real): raise SystemExit(f"adf: rejected {path!r}: not a directory")
    return real


def _state(entry):
    if not os.path.isdir(entry): return "missing"
    root = hook._git_root(entry)
    return "no-git: reads denied (project_not_git)" if root is None else "git-root" if root == os.path.realpath(entry) else f"subdir of git root {root}"


def cmd_list():
    for entry in _lines(): print(f"enabled  {entry}  [{_state(entry)}]" if hook._canonical(entry) else f"ignored  {entry}  [not canonical]")


def cmd_enable(path):
    real, lines = _canonical_arg(path), _lines()
    if real in lines: print(f"already enabled: {real}"); return
    if hook._git_root(real) is None: print(f"warning: {real} is not inside a git repository; the gate will deny reads there (project_not_git)", file=sys.stderr)
    _write(lines + [real]); print(f"enabled: {real}")


def cmd_disable(path):
    _require(path)
    real, lines = os.path.realpath(path), _lines()
    kept = [line for line in lines if line not in (path, real)]
    if kept != lines: _write(kept)
    print(f"disabled: {real}" if kept != lines else f"not enabled: {real}")


def _parse(text):
    try: return json.loads(text)
    except ValueError: return None


def _json(path):
    try: return _parse(path.read_text(encoding="utf-8"))
    except OSError: return None


def _granted(policy_file):
    """sub -> number of paths the pinned policy grants (ADR 0024); None when the policy is absent or unreadable."""
    config = _json(Path(policy_file)) if policy_file else None
    policy = (config or {}).get("policy") if isinstance(config, dict) else None
    if not isinstance(policy, dict): return None
    rules = policy.get("principal_rules")
    if isinstance(rules, list): return {rule.get("sub"): len(rule.get("allowed_scopes") or []) for rule in rules if isinstance(rule, dict)}
    host = len(policy.get("rules", [{}])[0].get("allowed_scopes") or []) if policy.get("rules") else 0
    return {"*": host}  # no principal_rules: every principal is granted the host allowlist


def _project_counts(project_dir):
    bundles, attempts, principals, paths = Counter(), Counter(), {}, {}
    for item in sorted(project_dir.rglob("*.json")):
        if "_attempts" in item.parts: continue
        body = _json(item)
        if not isinstance(body, dict): bundles["unreadable"] += 1; continue
        bundles[str((body.get("receipt") or {}).get("reason_code") or body.get("reason_code", "no_reason_code"))] += 1  # effect layer first, else PDP/edge
        if "_a2a" in item.parts and isinstance(body.get("principal"), dict):  # A2A record: who, outcome, bundle link
            principals.setdefault(str(body["principal"].get("sub")), []).append((body.get("outcome"), body.get("bundle_id")))
        elif isinstance(body.get("bundle_id"), str) and isinstance(body.get("effective_scope"), dict):
            paths[body["bundle_id"]] = body["effective_scope"].get("path")
    for item in sorted(project_dir.rglob("_attempts/*.jsonl")):
        try: events = [_parse(line) for line in item.read_text(encoding="utf-8").splitlines()]
        except OSError: attempts["unreadable"] += 1; continue
        started = next((event for event in events if isinstance(event, dict) and event.get("phase") == "started"), None)
        done = next((event for event in events if isinstance(event, dict) and event.get("phase") == "completed"), None)
        if done is None: attempts["incomplete"] += 1; continue
        payload = done.get("payload") or {}
        attempts[str(payload.get("reason_code", "no_reason_code"))] += 1
        sub = ((started or {}).get("payload") or {}).get("principal_sub")
        if isinstance(sub, str): principals.setdefault(sub, []).append((payload.get("outcome"), payload.get("bundle_id")))
    return bundles, attempts, principals, paths


def cmd_reasons(policy_file=None):
    evidence, granted = hook.adf_home() / "evidence", _granted(policy_file)
    projects = sorted(path for path in evidence.iterdir() if path.is_dir()) if evidence.is_dir() else []
    for project_dir in projects:
        bundles, attempts, principals, paths = _project_counts(project_dir)
        name = project_dir.name
        print(f"{name}  total={sum(bundles.values())}  " + " ".join(f"{code}={n}" for code, n in sorted(bundles.items())))
        if attempts: print(f"{name}  attempts={sum(attempts.values())}  " + " ".join(f"{code}={n}" for code, n in sorted(attempts.items())))
        for sub, outcomes in sorted(principals.items()):
            delivered = [bundle for outcome, bundle in outcomes if outcome == "delivered"]
            read = {paths.get(bundle) for bundle in delivered} - {None}
            line = f"{name}  principal={sub}  attempts={len(outcomes)} delivered={len(delivered)} denied={len(outcomes) - len(delivered)} paths_read={len(read)}"
            if granted is not None:
                allowed = granted.get(sub, granted.get("*"))
                line += f" granted={allowed} unused={max(allowed - len(read), 0)}" if allowed is not None else " granted=0 (not named in policy)"
            print(line)
    if not projects: print("no evidence yet")


def main(argv):
    commands = {"list": (cmd_list, 0), "enable": (cmd_enable, 1), "disable": (cmd_disable, 1), "reasons": (cmd_reasons, 0)}
    if argv[:1] == ["reasons"] and len(argv) == 3 and argv[1] == "--policy" and argv[2]: cmd_reasons(argv[2]); return 0
    if not argv or argv[0] not in commands or len(argv) - 1 != commands[argv[0]][1]: print(__doc__.strip(), file=sys.stderr); return 2
    commands[argv[0]][0](*argv[1:]); return 0


if __name__ == "__main__": raise SystemExit(main(sys.argv[1:]))
