#!/usr/bin/env python3
"""`make demo`: three real decisions on a throwaway fixture, then offline verification. Touches nothing of yours.

Runs the real `adf` CLI and the real `adf hook` (the PreToolUse entry point) with synthetic Claude-style payloads
against a temporary Git repository and a temporary HOME/ADF_HOME, then removes both. It never reads, writes or
registers anything in your ~/.claude, ~/.codex or ~/.adf, and the `.env` it creates holds a fake value.

  python3 ai-development-framework/e2e/demo.py      # or: make demo
  ADF_BIN=/path/to/adf   use that executable          DEMO_KEEP=1   keep the fixture and print where it is

Exit 0: every decision and verification matched. Exit 1: a decision differed or no decision came back (reported
as "no decision", never as a deny). Exit 2: a prerequisite is missing (adf, git), with how to fix it.
Stdlib only; no network.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CASES = (  # (label, tool, tool_input relative path key, path, expected permission, expected reason fragment, artifact)
    ("Read README.md", "Read", "file_path", "README.md", "allow", "delivered/read_delivered", "bundle"),
    ("Read .env", "Read", "file_path", ".env", "deny", "deny/invalid_scope", "bundle"),
    ("Edit .claude/settings.json", "Edit", "file_path", ".claude/settings.json", "deny", "uncovered_write_denied_agent_config", "journal"),
)


class Missing(Exception):
    """A prerequisite is absent; the message says how to recover."""


def _executable(candidate):
    return bool(candidate) and Path(candidate).is_file() and os.access(candidate, os.X_OK)


def find_adf():
    explicit = os.environ.get("ADF_BIN")
    if explicit:  # an explicit choice never falls back to another adf
        if _executable(explicit):
            return explicit
        raise Missing("ADF_BIN does not point to an executable adf. Unset it, or activate the venv and run `make install-dev`.")
    for candidate in (shutil.which("adf"), str(REPO / ".venv/bin/adf"), str(Path(sys.executable).parent / "adf")):
        if _executable(candidate):
            return candidate
    raise Missing("adf executable not found. From the clone: `python3 -m venv .venv && source .venv/bin/activate && make install-dev`, then rerun.")


def make_fixture(base):
    """Synthetic project: a public README, a fake .env and a .gitignore, committed so ADF can snapshot it."""
    if not shutil.which("git"):
        raise Missing("git not found on PATH; install Git and rerun.")
    repo = base / "my-app"
    repo.mkdir()
    (repo / "README.md").write_text("# my-app\n")
    (repo / ".env").write_text("DATABASE_URL=postgres://demo:not-a-real-secret@localhost/app\n")
    (repo / ".gitignore").write_text(".env\n")
    for args in (["init", "-q"], ["add", "-f", "."], ["-c", "user.name=demo", "-c", "user.email=demo@example.invalid", "commit", "-qm", "fixture"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return repo


def run(adf, args, env, stdin=None):
    return subprocess.run([adf, *args], input=stdin, capture_output=True, text=True, env=env, timeout=120)


def decision(adf, env, repo, tool, key, path):
    """-> (permission, reason) from the hook; ("none", "no decision") when it printed nothing."""
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "adf-demo", "tool_input": {key: str(repo / path), **({"old_string": "a", "new_string": "b"} if tool == "Edit" else {})}}
    proc = run(adf, ["hook"], {**env, "CLAUDE_PROJECT_DIR": str(repo)}, json.dumps(payload))
    out = proc.stdout.strip()
    if not out:
        return "none", "no decision"
    spec = json.loads(out).get("hookSpecificOutput") or {}
    return spec.get("permissionDecision", "none"), spec.get("permissionDecisionReason", "").removeprefix("adf: ")


def artifact(home, reason):
    """'bundle' when the reason names a bundle that exists; 'journal' when only an attempt journal recorded it."""
    if "bundle=" in reason and any((home / "evidence").rglob(reason.split("bundle=")[1] + ".json")):
        return "bundle"
    code = reason.split()[0].split("/")[-1]
    if any(code in p.read_text() for p in (home / "evidence").rglob("_attempts/*.jsonl")):
        return "journal"
    return "none"


def demo(adf, base, write=print):
    home_dir = base / "home"
    home = home_dir / ".adf"
    home.mkdir(parents=True)
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home_dir), "ADF_HOME": str(home), "ADF_EVIDENCE_KEY_FILE": str(home / "evidence.key")}
    repo = make_fixture(base)
    for args in (["projects", "enable", str(repo)], ["key", "init", str(home / "evidence.key")]):
        proc = run(adf, args, env)
        if proc.returncode != 0:
            raise RuntimeError(f"`adf {args[0]} {args[1]}` failed (exit {proc.returncode}); rerun with DEMO_KEEP=1 to inspect the fixture")
    write("ADF demo: synthetic fixture, real adf CLI and hook. No client settings, ~/.adf or real secret is touched.\n")
    ok, deny_reason = True, None
    for label, tool, key, path, want, fragment, want_artifact in CASES:
        permission, reason = decision(adf, env, repo, tool, key, path)
        got_artifact = artifact(home, reason) if permission != "none" else "none"
        match = permission == want and fragment in reason and got_artifact == want_artifact
        ok &= match
        shown = {"bundle": "Evidence Bundle", "journal": "attempt journal only", "none": "no record"}[got_artifact]
        code = reason.split(" bundle=")[0]
        write(f"  {'✓' if match else '✗'} {label:<28} {permission:<5} {code:<40} {shown}")
        if label == "Read .env" and got_artifact == "bundle":
            deny_reason = reason
    write("")
    if deny_reason:
        bundle = next((home / "evidence").rglob(deny_reason.split("bundle=")[1] + ".json"))
        for title, extra, expected in (("no key", [], "authenticity=not_checked"), ("demo host key", ["--key", str(home / "evidence.key")], "authenticity=valid")):
            out = run(adf, ["verify", str(bundle), *extra], env).stdout.strip()
            match = out.startswith("verified") and expected in out
            ok &= match
            write(f"  {'✓' if match else '✗'} {'adf verify (' + title + ')':<28} {out.split('  ', 1)[0]:<46} {expected}")
        write("\n  --key checks a shared-secret HMAC with this host's key; it is not public verification.")
    else:
        ok = False
        write("  ✗ no bundle for the .env decision, nothing to verify")
    return ok


def main():
    try:
        adf = find_adf()
    except Missing as error:
        print(f"adf demo: {error}", file=sys.stderr)
        return 2
    keep = os.environ.get("DEMO_KEEP") == "1"
    base = Path(tempfile.mkdtemp(prefix="adf-demo-"))
    try:
        ok = demo(adf, base)
    except Missing as error:
        print(f"adf demo: {error}", file=sys.stderr)
        return 2
    except (RuntimeError, subprocess.SubprocessError, OSError, ValueError) as error:
        print(f"adf demo: {error}", file=sys.stderr)
        return 1
    finally:
        if keep:
            print(f"\n  kept: {base} (DEMO_KEEP=1; remove it when done)")
        else:
            shutil.rmtree(base, ignore_errors=True)
    print("\n  fixture removed." if not keep else "", end="\n" if not keep else "")
    print("demo passed" if ok else "demo FAILED: a decision or verification differed from the expected contract")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
