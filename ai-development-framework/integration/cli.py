"""`adf`: one entry point over the existing control-plane scripts. Thin dispatch; no command changes behaviour.

  adf projects list|enable PATH|disable PATH|reasons [...]   host project list and aggregate (hooks/adf-projects.py)
  adf hook                                                   the global PreToolUse hook (stdin JSON; hooks/adf-read-hook.py)
  adf hook-snippet [claude|codex]                            print the hook registration for this clone, fail-safe included
  adf policy build --run-id ID --allow PATH ... --out FILE   build a pinned host policy (policy pack effect-security-read-v0)
  adf a2a serve | a2a mint SUB SCOPE [...]                    loopback A2A gateway and its pilot-only HS256 token double
  adf verify FILE                                            verify an EvidenceBundle or an A2AEvidenceRecord offline
  adf version

Arguments after the command go to the underlying script unchanged. Editable install only (`make install-dev`):
the hook and policy scripts live in the clone, not in the package.
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # ai-development-framework/


def _script(relative):
    """Hooks and the pack builder are scripts with dashes in their names, not importable modules."""
    path = ROOT / relative
    if not path.is_file():
        raise FileNotFoundError(relative)
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _usage(code=2):
    print(__doc__.strip(), file=sys.stderr)
    return code


def cmd_projects(argv): return _script("hooks/adf-projects.py").main(argv)


def cmd_hook(argv):
    """Never blocks the agent on an ADF failure: exit 0 and no output means 'no decision' (the hook's own rule)."""
    if argv:
        return _usage()
    try:
        return _script("hooks/adf-read-hook.py").main()
    except Exception:
        return 0


def cmd_hook_snippet(argv):
    agent = argv[0] if argv else "claude"
    if agent not in ("claude", "codex") or len(argv) > 1:
        return _usage()
    adf = Path(sys.executable).parent / "adf"
    command = f'A={adf}; [ -x "$A" ] || exit 0; exec "$A" hook'  # missing binary: no decision, never a blocked tool
    hook = {"type": "command", "timeout": 30, "command": command}
    entries = [{"matcher": "Read", "hooks": [hook]}, {"matcher": "Bash", "hooks": [hook]}] if agent == "claude" else [{"matcher": "^Bash$", "hooks": [{**hook, "statusMessage": "Checking ADF read policy"}]}]
    target = "~/.claude/settings.json" if agent == "claude" else "~/.codex/hooks.json"
    print(f"// add to hooks.PreToolUse in {target}; existing hooks keep running (they add up)", file=sys.stderr)
    print(json.dumps({"hooks": {"PreToolUse": entries}}, indent=2))
    return 0


def cmd_policy(argv):
    if argv[:1] != ["build"]:
        return _usage()
    return _script("policy-packs/effect-security-read-v0/build.py").main(argv[1:])


def cmd_a2a(argv):
    from integration.a2a_gateway import _main
    return _main(argv)


def cmd_verify(argv):
    """Offline, no network, no LLM. Exit 0 verified, 1 not verified, 2 unusable input."""
    if len(argv) != 1:
        return _usage()
    from integration.a2a_gateway import verify_record
    from integration.local_evidence_bundle import verify_offline
    from integration.local_read_adapter import schemas
    path = Path(argv[0])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"adf: cannot read {path}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        return 2
    if data.get("edge_id") == "a2a":  # A2AEvidenceRecord in <evidence>/_a2a/: its bundle lives in <evidence>/<run>/
        bundle = None
        if data.get("bundle_id"):
            found = sorted(path.resolve().parent.parent.glob(f"*/{data['bundle_id']}.json"))
            if not found:
                print(f"NOT verified  a2a_record  bundle {data['bundle_id']} not found next to the record")
                return 1
            bundle = json.loads(found[0].read_text(encoding="utf-8"))
        ok, kind = verify_record(data, bundle, schemas()), "a2a_record"
    else:
        ok, kind = verify_offline(data, schemas()), "evidence_bundle"
    print(f"{'verified' if ok else 'NOT verified'}  {kind}  reason_code={data.get('reason_code')}")
    return 0 if ok else 1


def cmd_version(argv):
    for candidate in (ROOT / "VERSION", ROOT.parent / "VERSION"):
        if candidate.is_file():
            print(candidate.read_text(encoding="utf-8").strip())
            return 0
    return 1


COMMANDS = {"projects": cmd_projects, "hook": cmd_hook, "hook-snippet": cmd_hook_snippet, "policy": cmd_policy, "a2a": cmd_a2a, "verify": cmd_verify, "version": cmd_version}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        return _usage(0 if argv[:1] in (["-h"], ["--help"], ["help"]) else 2)
    try:
        return COMMANDS[argv[0]](argv[1:])
    except FileNotFoundError as missing:
        print(f"adf: {missing} not found; adf runs from an editable clone (make install-dev)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
