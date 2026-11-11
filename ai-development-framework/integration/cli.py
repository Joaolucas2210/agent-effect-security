"""`adf`: one entry point over the existing control-plane scripts. Thin dispatch; no command changes behaviour.

  adf projects list|enable PATH|disable PATH|reasons [...]   host project list and aggregate (integration/projects.py)
  adf hook                                                   the global PreToolUse hook (stdin JSON; integration/read_hook.py)
  adf hook-snippet [claude|codex]                            print the hook registration for this clone, fail-safe included
  adf policy build --run-id ID --allow PATH ... --out FILE   build a pinned host policy (policy pack effect-security-read-v0)
  adf a2a serve | a2a mint SUB SCOPE [...]                    loopback A2A gateway and its pilot-only HS256 token double
  adf verify FILE [--key KEYFILE]                            verify an EvidenceBundle or an A2AEvidenceRecord offline; --key also checks the host signature (ADR 0030)
  adf key init [KEYFILE]                                     create the host evidence key (0400, never overwritten); default $ADF_HOME/evidence.key
  adf mcp pin FILE                                           validate a host MCP registry and print its pin (ADR 0031); export ADF_MCP_REGISTRY_FILE/_SHA256
  adf mcp probe FILE [--write]                               start each pinned server, digest its live tool list, compare (exit 1 on any change/unpinned); --write records digests, then re-pin
  adf doctor [--pin]                                         check the control plane against $ADF_HOME/pins.json (exit 0 intact, 1 tampered, 3 not pinned); --pin (re)writes it (ADR 0027); with a registry also MCP definition drift and probe age (ADF_MCP_PROBE_MAX_AGE_DAYS, default 30); always reports the read policy in effect (pinned / reference demo / host_policy_invalid), without changing the exit code
  adf version

Arguments after the command go to the underlying script unchanged. Supported install: the source clone, editable
(`make install-dev`). A wheel carries the packages, the hook modules and their JSON contracts: every command but
policy build (its script lives in the clone; exit 2) works from it, and `adf hook` decides exactly as in the clone.
A hook module that cannot load makes no decision; doctor and hook-snippet then print NOT PROTECTED.
"""
import importlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # ai-development-framework/


_MODULES = {"hooks/adf-read-hook.py": "integration.read_hook", "hooks/adf-projects.py": "integration.projects"}


def _script(relative):
    """The hook and the project list are package modules (the hooks/ files are checkout shims running the same source),
    so clone and wheel run one implementation. The pack builder is a clone script with dashes in its name."""
    if relative in _MODULES:
        return importlib.import_module(_MODULES[relative])
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


_POLICY_ENV = ("ADF_READ_POLICY_FILE", "ADF_READ_POLICY_SHA256")
DEMO_POLICY_WARNING = ("no pinned read policy (ADF_READ_POLICY_FILE/ADF_READ_POLICY_SHA256 unset): enabled projects run the "
                       "reference demo policy, which grants each requested non-sensitive path; it is not a reviewed allowlist")


def read_policy_status(lookup):
    """Diagnostic only, mirrors read_gate_host.host_policy_settings + load_host_policy; never changes a decision.
    `lookup(name)` -> value or None. -> ("demo", None) | ("pinned", policy_id) | ("invalid", detail). Path-free."""
    path, pin = (lookup(name) for name in _POLICY_ENV)
    if path is None and pin is None:
        return "demo", None
    if path is None or pin is None:
        return "invalid", "partial: both variables are required"
    if not Path(path).is_absolute():
        return "invalid", "file path is not absolute"
    if not Path(path).is_file():
        return "invalid", "file missing"
    from integration.local_read_adapter import load_host_policy, schemas
    try:
        config = load_host_policy(path, pin, schemas())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "invalid", "file unreadable or not JSON"
    except Exception:
        return "invalid", "pin mismatch or not a host policy envelope"
    return "pinned", config["policy"].get("policy_id")


def _policy_line(status, detail):
    if status == "demo":
        return f"  ! read policy: reference demo — {DEMO_POLICY_WARNING}"
    if status == "invalid":
        return f"  ✗ read policy: host_policy_invalid ({detail}): every read in an enabled project is denied"
    return f"  read policy: pinned host policy, pin verified (policy_id={detail})"


def cmd_projects(argv): return _script("hooks/adf-projects.py").main(argv)


def hook_runtime_problem():
    """Diagnostic only, never changes a decision: None when `adf hook` can load itself and every gate, else what breaks."""
    try:
        hook = _script("hooks/adf-read-hook.py")
    except Exception as exc:  # cmd_hook turns the same failure into exit 0, no output
        return (f"NOT PROTECTED: the hook module cannot load ({type(exc).__name__}): `adf hook` makes no decision, "
                "so every tool call runs under the client's own permissions")
    try:
        hook.load_gates()
    except Exception as exc:  # decide() turns the same failure into adapter_failed for enabled projects
        return f"hook gates cannot load ({type(exc).__name__}): every gated tool call in an enabled project is denied (adapter_failed)"
    return None


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
    import os
    adf = Path(sys.executable).parent / "adf"
    command = f'A={adf}; [ -x "$A" ] || exit 0; exec "$A" hook'  # missing binary: no decision, never a blocked tool
    key = os.environ.get("ADF_EVIDENCE_KEY_FILE") or (lambda p: str(p) if p.is_file() else None)(Path(os.environ.get("ADF_HOME") or Path.home() / ".adf") / "evidence.key")
    if key:
        command = f"export ADF_EVIDENCE_KEY_FILE={key}; " + command  # ADR 0030: the env travels with the registration, no shell profile needed
    hook = {"type": "command", "timeout": 30, "command": command}
    entries = [{"matcher": "Read", "hooks": [hook]}, {"matcher": "Bash", "hooks": [hook]}, {"matcher": "Grep|Glob|Edit|Write|MultiEdit|NotebookEdit|WebFetch", "hooks": [hook]}, {"matcher": "mcp__.*", "hooks": [hook]}] if agent == "claude" else [{"matcher": "^Bash$", "hooks": [{**hook, "statusMessage": "Checking ADF read policy"}]}]
    target = "~/.claude/settings.json" if agent == "claude" else "~/.codex/hooks.json"
    print(f"// add to hooks.PreToolUse in {target}; existing hooks keep running (they add up)", file=sys.stderr)
    problem = hook_runtime_problem()  # stderr only: the JSON on stdout is unchanged
    if problem:
        print(f"// warning: {problem}; reinstall (clone: make install-dev; wheel: pip install it again) and check with `adf doctor`", file=sys.stderr)
    if all(os.environ.get(name) is None for name in _POLICY_ENV):  # stderr only: the JSON on stdout is unchanged
        print(f"// warning: {DEMO_POLICY_WARNING}; build one with `adf policy build` and check with `adf doctor`", file=sys.stderr)
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
    key = None
    if len(argv) == 3 and argv[1] == "--key":
        from integration.evidence_signing import SigningUnavailable, load_key
        try:
            key = load_key(Path(argv[2]))
        except SigningUnavailable as exc:
            print(f"adf: key unusable ({exc})", file=sys.stderr)
            return 2
        argv = argv[:1]
    if len(argv) != 1:
        return _usage()
    from integration.a2a_gateway import verify_record
    from integration.evidence_signing import verify_file
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
    authenticity = verify_file(path, key)  # integrity (above) and authenticity are reported separately; both must hold with --key
    ok = ok and authenticity in ("valid", "not_checked")
    mode = f"  delivery_mode={data['delivery_mode']}" if "delivery_mode" in data else ""
    print(f"{'verified' if ok else 'NOT verified'}  {kind}  reason_code={data.get('reason_code')}  authenticity={authenticity}{mode}")
    return 0 if ok else 1


def cmd_key(argv):
    """`adf key init [KEYFILE]`: a human creates the host evidence key; refuses to overwrite."""
    if not argv or argv[0] != "init" or len(argv) > 2:
        return _usage()
    import os
    from integration.evidence_signing import init_key
    target = Path(argv[1]) if len(argv) == 2 else Path(os.environ.get("ADF_HOME") or Path.home() / ".adf") / "evidence.key"
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        init_key(target)
    except FileExistsError:
        print(f"adf: {target} exists; a key is never overwritten", file=sys.stderr)
        return 1
    print(f"export ADF_EVIDENCE_KEY_FILE={target}")
    return 0


def cmd_mcp(argv):
    """`adf mcp pin FILE`: the human computes the pin once, after review; the gate never recomputes it.
    `adf mcp probe FILE [--write]`: human-run tool-list digest check (ADR 0031 slice 2); never called by a hook."""
    if argv[:1] == ["probe"] and len(argv) in (2, 3) and (len(argv) == 2 or argv[2] == "--write"):
        return _mcp_probe(Path(argv[1]), len(argv) == 3)
    if len(argv) != 2 or argv[0] != "pin":
        return _usage()
    from integration.mcp_registry import RegistryInvalid, pin
    try:
        fingerprint = pin(json.loads(Path(argv[1]).read_text(encoding="utf-8")))
    except (OSError, ValueError, RegistryInvalid) as exc:
        print(f"adf: registry rejected ({exc})", file=sys.stderr)
        return 1
    print(f"export ADF_MCP_REGISTRY_FILE={Path(argv[1]).resolve()}\nexport ADF_MCP_REGISTRY_SHA256={fingerprint}")
    return 0


def _mcp_probe(path, write):
    import asyncio
    from integration.mcp_registry import RegistryInvalid, probe, record_probe, validate
    try:
        registry = validate(json.loads(path.read_text(encoding="utf-8")))
        report = asyncio.run(probe(registry))
    except (OSError, ValueError, RegistryInvalid) as exc:
        print(f"adf: registry rejected ({exc})", file=sys.stderr)
        return 2
    bad = False
    for name, item in report.items():
        print(f"  {name}: {item['status']}" + (f"  tools_sha256={item['tools_sha256']}" if "tools_sha256" in item else ""))
        if item["status"] in ("unpinned", "mcp_tool_list_changed", "unreachable"):
            bad = True
    if write:
        path.write_text(json.dumps(record_probe(registry, report), indent=2, sort_keys=True) + "\n")
        print(f"wrote digests to {path}; re-pin with: adf mcp pin {path}")
        return 0 if all(item["status"] != "unreachable" for item in report.values()) else 1
    return 1 if bad else 0


def cmd_doctor(argv):
    """ADR 0027. A human pins; the gates only compare. Not pinned is exit 3, never green."""
    import os
    from integration.control_plane_pins import check, clone_line, snapshot, write_manifest
    if argv not in ([], ["--pin"]):
        return _usage()
    adf_home = Path(os.environ.get("ADF_HOME") or Path.home() / ".adf")
    if argv:
        adf_home.mkdir(parents=True, exist_ok=True, mode=0o700)
        snap = snapshot(ROOT, adf_home)
        write_manifest(adf_home / "pins.json", snap)
        print(f"pinned {len(snap['files'])} file(s), registration {snap['registration']} -> {adf_home / 'pins.json'}")
        return 0
    print(f"clone: {clone_line(ROOT)}")
    problem = hook_runtime_problem()
    if problem:  # diagnostic only: exit codes unchanged
        print(f"  ✗ {problem}")
    from integration.control_plane_pins import registered_env
    registered = registered_env(os.environ.get("HOME") or str(Path.home()))  # shell first, else the registered Claude hook command
    print(_policy_line(*read_policy_status(lambda name: os.environ[name] if name in os.environ else registered.get(name))))  # diagnostic only: exit codes unchanged
    divergent = check(ROOT, adf_home)
    if divergent is None:
        print("not pinned: run `adf doctor --pin` after reviewing the install (ADR 0027)")
        return 3
    for label in divergent:
        print(f"  ✗ {label}")
    print("control_plane_tampered" if divergent else "control plane intact")
    mcp_bad = _doctor_mcp(os.environ.get("ADF_TRUSTED_REPOSITORY") or os.getcwd(), os.environ.get("HOME") or str(Path.home()))
    return 1 if divergent or mcp_bad else 0


def _doctor_mcp(root, home):
    """ADR 0031 follow-up: definition drift in every client config, offline. True when something changed or is unreadable."""
    import os
    from integration.mcp_registry import RegistryInvalid, configured, drift, load, probe_status
    try:
        config = configured()
        if config is None:
            return False
        registry = load(*config)
        report = drift(registry, root, home)
        max_age = int(os.environ.get("ADF_MCP_PROBE_MAX_AGE_DAYS", "30"))
        if max_age < 0:
            raise ValueError
        ages = probe_status(registry, max_age)
    except RegistryInvalid:
        print("  ✗ mcp registry: mcp_registry_invalid")
        return True
    except ValueError:
        print("  ✗ ADF_MCP_PROBE_MAX_AGE_DAYS must be a non-negative integer (days)")
        return True
    bad = False
    for name, clients in report.items():
        age = ages.get(name, {"status": "never"})
        probe = age["status"] + (f"({age['age_days']}d)" if "age_days" in age else "")
        print(f"  mcp {name}: " + " ".join(f"{client}={status}" for client, status in clients.items()) + f" probe={probe}")
        bad = bad or any(status in ("changed", "unreadable") for status in clients.values()) or age["status"] != "fresh"
    return bad


def cmd_version(argv):
    for candidate in (ROOT / "VERSION", ROOT.parent / "VERSION"):
        if candidate.is_file():
            print(candidate.read_text(encoding="utf-8").strip())
            return 0
    from importlib.metadata import PackageNotFoundError, version  # wheel install: no clone VERSION, the metadata carries it
    try:
        print(version("adf-control-plane"))
    except PackageNotFoundError:
        return 1
    return 0


COMMANDS = {"projects": cmd_projects, "hook": cmd_hook, "hook-snippet": cmd_hook_snippet, "policy": cmd_policy, "a2a": cmd_a2a, "verify": cmd_verify, "key": cmd_key, "mcp": cmd_mcp, "doctor": cmd_doctor, "version": cmd_version}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        return _usage(0 if argv[:1] in (["-h"], ["--help"], ["help"]) else 2)
    try:
        return COMMANDS[argv[0]](argv[1:])
    except FileNotFoundError as missing:
        print(f"adf: {missing} not found; this command runs from the source clone (editable install: make install-dev), not from a wheel", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
