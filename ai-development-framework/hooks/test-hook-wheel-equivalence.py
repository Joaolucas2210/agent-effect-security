"""R-13 / Phase 2C: `adf hook` from a non-editable wheel decides exactly like the source clone.

Builds sdist -> wheel offline (helpers shared with test-packaging-wheel.py), installs it into a throwaway venv, and
feeds the same ordered PreToolUse payloads to three runners against a synthetic git repo, each with its own scratch
HOME/ADF_HOME: the installed `adf hook` (wheel), `integration.cli main(['hook'])` from the clone, and the clone's
direct script registration `hooks/adf-read-hook.py`. Outputs must be identical after normalising bundle ids;
exit codes 0 and empty stderr everywhere. Then, wheel only:
  - real decisions: a tracked file is allowed, a dummy `.env` is denied with the clone's reason code, evidence
    (bundles + attempt journals) is written under the scratch ADF_HOME and `adf verify` accepts the allow bundle;
  - ADR 0027: `adf doctor --pin` (scratch ADF_HOME only) pins the installed hook modules; editing one is
    `control_plane_tampered` for the hook and exit 1 for doctor;
  - a missing hook module is no decision (ADR 0037 unchanged), and `adf doctor` / `adf hook-snippet` say NOT PROTECTED.
And clone only: the same NOT PROTECTED state when the hook module cannot be imported.

The repo, the project .venv, the real ~/.adf, ~/.claude and ~/.codex are never touched. Missing tooling prints
SKIPPED and exits 77; ADF_PACKAGING_REQUIRED=1 turns a skip into a failure.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("packaging_wheel", ROOT / "hooks/test-packaging-wheel.py")
pw = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(pw)
CONTRACTS = os.environ.get("ADF_CONTRACTS_PYTHON") or sys.executable
CLI = "import sys; sys.path.insert(0, sys.argv[1]); from integration.cli import main; raise SystemExit(main(sys.argv[2:]))"
BROKEN_CLI = "import sys; sys.modules['integration.read_hook'] = None; " + CLI.split("; ", 1)[1]  # the hook module cannot be imported
HOOK_MODULES = ("integration/read_hook.py", "integration/claude_read_gate.py", "integration/codex_bash_read_gate.py", "integration/deny_gate.py", "integration/projects.py")
BUNDLE = re.compile(r"bundle=[0-9a-f-]+")


def git(repo, *args): subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], check=True, capture_output=True)


def make_repo(path):
    path.mkdir(parents=True)
    (path / "README.md").write_text("public\n"); (path / ".env").write_text("TOKEN=not-a-real-secret\n")
    (path / "src").mkdir(); (path / "src/app.py").write_text("print('hi')\n")
    git(path, "init", "-q"); git(path, "add", "-f", "."); git(path, "commit", "-qm", "f")
    return path


def cases(repo, adf_home):
    """Ordered: the WebFetch case depends on the sensitive attempts earlier in the same run (ADR 0028 1c)."""
    def p(tool, tool_input, **extra): return {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "eq-run", "cwd": str(repo), "tool_input": tool_input, **extra}
    return [
        ("read-tracked", p("Read", {"file_path": f"{repo}/README.md"}), {}),
        ("read-subdir", p("Read", {"file_path": f"{repo}/src/app.py"}), {}),
        ("read-sensitive", p("Read", {"file_path": f"{repo}/.env"}), {}),
        ("read-outside", p("Read", {"file_path": "/etc/hostname"}), {}),
        ("read-extra-key", p("Read", {"file_path": f"{repo}/README.md", "bogus": 1}), {}),
        ("read-bad-agent-type", p("Read", {"file_path": f"{repo}/README.md"}, agent_type="bad type!"), {}),
        ("bash-cat-tracked", p("Bash", {"command": "cat README.md"}), {}),
        ("bash-cat-sensitive", p("Bash", {"command": "cat .env"}), {}),
        ("bash-head-sensitive", p("Bash", {"command": "head -n 1 .env"}), {}),
        ("bash-other", p("Bash", {"command": "ls -la"}), {}),
        ("grep-sensitive", p("Grep", {"pattern": "x", "path": ".env"}), {}),
        ("glob-tracked", p("Glob", {"pattern": "*.md", "path": "src"}), {}),
        ("edit-sensitive", p("Edit", {"file_path": f"{repo}/.env", "old_string": "a", "new_string": "b"}), {}),
        ("write-agent-config", p("Write", {"file_path": f"{repo}/.claude/settings.json", "content": "{}"}), {}),
        ("write-adf-home", p("Write", {"file_path": f"{adf_home}/enabled-projects", "content": ""}), {}),
        ("webfetch-after-sensitive", p("WebFetch", {"url": "https://example.invalid", "prompt": "x"}), {}),
        ("mcp-unconfigured", p("mcp__srv__tool", {}), {}),
        ("unsupported-tool", p("Teleport", {}), {}),
        ("malformed", "{not json", {}),
        ("codex-shape-cat", p("Bash", {"command": "cat README.md"}), {"CLAUDE_PROJECT_DIR": None}),
        ("not-enabled", p("Read", {"file_path": "/x/README.md"}, cwd="/"), {"CLAUDE_PROJECT_DIR": "/"}),
    ]


def payload(repo, adf_home, wanted):
    return json.dumps(next(body for name, body, _ in cases(repo, adf_home) if name == wanted))


def run_matrix(runner, repo, home, base_env):
    """-> [(case, raw stdout)]; asserts the client contract (exit 0, nothing on stderr) on every call."""
    out = []
    for name, payload, overrides in cases(repo, home / ".adf"):
        env = {**base_env, "HOME": str(home), "ADF_HOME": str(home / ".adf"), "CLAUDE_PROJECT_DIR": str(repo)}
        for key, value in overrides.items():
            env.pop(key) if value is None else env.__setitem__(key, value)
        proc = pw.run(runner, input=payload if isinstance(payload, str) else json.dumps(payload), env=env, cwd=str(repo))
        assert (proc.returncode, proc.stderr) == (0, ""), (name, runner[-1], proc.returncode, proc.stderr[-600:])
        out.append((name, proc.stdout.strip()))
    return out


def normal(matrix): return [(name, BUNDLE.sub("bundle=<id>", text)) for name, text in matrix]


def reason(text): return json.loads(text)["hookSpecificOutput"]["permissionDecisionReason"] if text else None


def evidence_shape(adf_home):
    """Path-free summary of what the hook persisted: bundle and journal counts plus reason codes."""
    root = adf_home / "evidence"
    bundles = [p for p in root.rglob("*.json") if "_attempts" not in p.parts]
    journals = sorted(root.rglob("_attempts/*.jsonl"))
    codes = sorted(json.loads(line).get("payload", {}).get("reason_code") or "" for j in journals for line in j.read_text().splitlines() if '"completed"' in line)
    return {"bundles": len(bundles), "journals": len(journals), "completed_reason_codes": codes}


def adf(venv_bin, *args, env, cwd):
    return pw.run([venv_bin / "adf", *args], env=env, cwd=cwd)


def main():
    required = os.environ.get("ADF_PACKAGING_REQUIRED") == "1"
    with tempfile.TemporaryDirectory(prefix="adf-hook-wheel-") as temp:
        scratch = Path(temp).resolve()
        try:
            summary = scenario(scratch)
        except pw.Skip as why:
            print(f"SKIPPED hook-wheel-equivalence: {why}")
            return 1 if required else 77
        except AssertionError as failure:
            print(f"✗ hook-wheel-equivalence: {failure}")
            return 1
    print(f"✓ hook-wheel-equivalence: {summary}")
    return 0


def install(scratch):
    python, origin = pw.build_python(scratch)
    source, dist = scratch / "src", scratch / "dist"
    source.mkdir(); dist.mkdir()
    pw.copy_sources(source)
    _, wheel = pw.build(python, source, dist)
    probe = pw.run([CONTRACTS, "-c", "import os, jsonschema; print(os.path.dirname(os.path.dirname(jsonschema.__file__)))"])
    if probe.returncode != 0:
        raise pw.Skip(f"jsonschema not importable from {CONTRACTS} (make install-dev)")
    venv = scratch / "run-venv"
    if pw.run([CONTRACTS, "-m", "venv", venv]).returncode != 0:
        raise pw.Skip(f"`{CONTRACTS} -m venv` unavailable")
    pw.check(pw.run([venv / "bin/python", "-m", "pip", "install", "--disable-pip-version-check", "--no-index", "--no-deps", "-q", wheel], cwd=str(scratch)), "pip install wheel")
    purelib = Path(pw.check(pw.run([venv / "bin/python", "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"]), "purelib").stdout.strip())
    (purelib / "zz-adf-hook-test-deps.pth").write_text(probe.stdout.strip() + "\n")  # runtime deps borrowed read-only
    return venv, purelib, origin


def scenario(scratch):
    venv, purelib, origin = install(scratch)
    vbin = venv / "bin"
    base_env = {"PATH": f"{vbin}:{os.environ.get('PATH', '/usr/bin:/bin')}", "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1", "ADF_OTEL_ENABLED": "0"}
    repo = make_repo(scratch / "proj")
    homes = {name: scratch / f"home-{name}" for name in ("wheel", "clone-cli", "clone-script", "pinned", "broken")}
    for home in homes.values():
        (home / ".adf").mkdir(parents=True); (home / ".adf/enabled-projects").write_text(f"{repo}\n")

    where = pw.check(pw.run([vbin / "python", "-c", "import integration.read_hook as m; print(m.__file__)"], env=base_env, cwd=str(scratch)), "import integration.read_hook").stdout.strip()
    assert Path(where).is_relative_to(venv), f"the wheel's hook module must come from the venv, not the clone: {where}"

    clone_env = {**base_env, "PYTHONPATH": str(ROOT)}
    runners = {
        "wheel": ([vbin / "adf", "hook"], base_env),
        "clone-cli": ([CONTRACTS, "-c", CLI, ROOT, "hook"], clone_env),
        "clone-script": ([CONTRACTS, ROOT / "hooks/adf-read-hook.py"], clone_env),
    }
    raw = {name: run_matrix(runner, repo, homes[name], env) for name, (runner, env) in runners.items()}
    results = {name: normal(matrix) for name, matrix in raw.items()}
    for name in ("clone-cli", "clone-script"):
        diff = [(a, b) for a, b in zip(results["wheel"], results[name]) if a != b]
        assert not diff, f"wheel vs {name} differ: {diff[:3]}"
    shapes = {name: evidence_shape(homes[name] / ".adf") for name in runners}
    assert shapes["wheel"] == shapes["clone-cli"] == shapes["clone-script"], shapes

    # real decisions, not pass-through
    got = dict(raw["wheel"])
    allow = json.loads(got["read-tracked"])["hookSpecificOutput"]
    assert allow["permissionDecision"] == "allow" and "delivered/" in allow["permissionDecisionReason"], allow
    deny = json.loads(got["read-sensitive"])["hookSpecificOutput"]
    assert deny["permissionDecision"] == "deny", deny
    sensitive_code = deny["permissionDecisionReason"].split("/", 1)[1].split()[0]
    assert sensitive_code == reason(dict(raw["clone-cli"])["read-sensitive"]).split("/", 1)[1].split()[0]
    assert "uncovered_write_denied_sensitive" in reason(got["edit-sensitive"]), got["edit-sensitive"]
    assert "uncovered_network_denied_after_sensitive_read" in reason(got["webfetch-after-sensitive"]), got["webfetch-after-sensitive"]
    assert got["codex-shape-cat"] == "{}" and got["not-enabled"] == "" and got["mcp-unconfigured"] == "", got
    assert shapes["wheel"]["bundles"] >= 2 and shapes["wheel"]["journals"] >= 1, shapes["wheel"]
    bundle_id = re.search(r"bundle=([0-9a-f-]+)", allow["permissionDecisionReason"])[1]
    bundle = next((homes["wheel"] / ".adf/evidence").rglob(f"{bundle_id}.json"))
    verified = adf(vbin, "verify", bundle, env=base_env, cwd=str(scratch))
    assert verified.returncode == 0 and verified.stdout.startswith("verified  evidence_bundle"), verified.stdout

    # healthy wheel: no false alarm; snippet JSON identical to the clone's (modulo the adf path)
    wheel_env = {**base_env, "HOME": str(homes["wheel"]), "ADF_HOME": str(homes["wheel"] / ".adf")}
    snippet = adf(vbin, "hook-snippet", "claude", env=wheel_env, cwd=str(scratch))
    assert snippet.returncode == 0 and "NOT PROTECTED" not in snippet.stderr and "no source clone" not in snippet.stderr, snippet.stderr
    clone_snippet = pw.run([CONTRACTS, "-c", CLI, ROOT, "hook-snippet", "claude"], env={**clone_env, "HOME": str(homes["wheel"]), "ADF_HOME": str(homes["wheel"] / ".adf")})
    assert snippet.stdout.replace(str(vbin / "adf"), "ADF") == clone_snippet.stdout.replace(str(Path(CONTRACTS).parent / "adf"), "ADF"), (snippet.stdout, clone_snippet.stdout)
    assert "NOT PROTECTED" not in clone_snippet.stderr, clone_snippet.stderr
    doctor = adf(vbin, "doctor", env=wheel_env, cwd=str(scratch))
    assert doctor.returncode == 3 and "NOT PROTECTED" not in doctor.stdout, (doctor.returncode, doctor.stdout)

    # ADR 0027 in the wheel layout: the modules that run are pinned, and editing one is tampering
    pin_env = {**base_env, "HOME": str(homes["pinned"]), "ADF_HOME": str(homes["pinned"] / ".adf"), "CLAUDE_PROJECT_DIR": str(repo)}
    pinned = adf(vbin, "doctor", "--pin", env=pin_env, cwd=str(scratch))
    assert pinned.returncode == 0, pinned.stdout + pinned.stderr
    files = json.loads((homes["pinned"] / ".adf/pins.json").read_text())["files"]
    unpinned = [label for label in HOOK_MODULES if not files.get(label)]
    assert not unpinned, f"hook modules not pinned with a digest: {unpinned}"
    assert adf(vbin, "doctor", env=pin_env, cwd=str(scratch)).returncode == 0
    edit = payload(repo, homes["pinned"] / ".adf", "edit-sensitive")
    assert "uncovered_write_denied_sensitive" in pw.run([vbin / "adf", "hook"], input=edit, env=pin_env, cwd=str(repo)).stdout
    with open(purelib / "integration/deny_gate.py", "a", encoding="utf-8") as handle:
        handle.write("\n# tampered\n")
    tampered = pw.run([vbin / "adf", "hook"], input=edit, env=pin_env, cwd=str(repo))
    assert "control_plane_tampered" in reason(tampered.stdout.strip()), tampered.stdout
    doctor = adf(vbin, "doctor", env=pin_env, cwd=str(scratch))
    assert doctor.returncode == 1 and "integration/deny_gate.py" in doctor.stdout, doctor.stdout

    # broken runtime: no decision (ADR 0037 is Proposed; behaviour unchanged), and said out loud
    for stale in [purelib / "integration/read_hook.py", *purelib.glob("integration/__pycache__/read_hook.*")]:
        stale.unlink()
    broken_env = {**base_env, "HOME": str(homes["broken"]), "ADF_HOME": str(homes["broken"] / ".adf"), "CLAUDE_PROJECT_DIR": str(repo)}
    read = payload(repo, homes["broken"] / ".adf", "read-tracked")
    hook = pw.run([vbin / "adf", "hook"], input=read, env=broken_env, cwd=str(repo))
    assert (hook.returncode, hook.stdout, hook.stderr) == (0, "", ""), (hook.returncode, hook.stdout, hook.stderr)
    assert not (homes["broken"] / ".adf/evidence").exists(), "no decision leaves no record"
    doctor = adf(vbin, "doctor", env=broken_env, cwd=str(scratch))
    assert doctor.returncode == 3 and "NOT PROTECTED" in doctor.stdout, doctor.stdout
    snippet = adf(vbin, "hook-snippet", env=broken_env, cwd=str(scratch))
    assert snippet.returncode == 0 and "NOT PROTECTED" in snippet.stderr and json.loads(snippet.stdout)["hooks"]["PreToolUse"], snippet.stderr

    # clone: the same explicit state when the module cannot be imported
    clone_broken = {**clone_env, "HOME": str(homes["broken"]), "ADF_HOME": str(homes["broken"] / ".adf"), "CLAUDE_PROJECT_DIR": str(repo)}
    hook = pw.run([CONTRACTS, "-c", BROKEN_CLI, ROOT, "hook"], input=read, env=clone_broken)
    assert (hook.returncode, hook.stdout) == (0, ""), (hook.returncode, hook.stdout, hook.stderr)
    doctor = pw.run([CONTRACTS, "-c", BROKEN_CLI, ROOT, "doctor"], env=clone_broken)
    assert "NOT PROTECTED" in doctor.stdout, doctor.stdout
    snippet = pw.run([CONTRACTS, "-c", BROKEN_CLI, ROOT, "hook-snippet"], env=clone_broken)
    assert "NOT PROTECTED" in snippet.stderr, snippet.stderr

    allowed = sum(1 for _, text in raw["wheel"] if '"allow"' in text)
    denied = sum(1 for _, text in raw["wheel"] if '"deny"' in text)
    return (f"wheel ({origin}) == clone cli == clone script on {len(results['wheel'])} payloads ({allowed} allow, {denied} deny, "
            f"sensitive={sensitive_code}); evidence {shapes['wheel']['bundles']} bundles / {shapes['wheel']['journals']} journals, adf verify ok; "
            f"{len(HOOK_MODULES)} hook modules pinned, tamper denied; missing module = no decision + NOT PROTECTED (wheel and clone)")


if __name__ == "__main__":
    raise SystemExit(main())
