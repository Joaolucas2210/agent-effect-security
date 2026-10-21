"""Check host deployments separately from package integrity; never install them."""
import json
import sys
from pathlib import Path


def check_host_deployment(core):
    core = Path(core).resolve()
    host = core.parent
    runner = host / "Makefile.adf"
    portable = runner.is_file() and not runner.is_symlink()
    failures, skipped = 0, 0
    paths = [".codex/hooks.json", ".github/workflows/quality-gates.yml", ".github/workflows/maintenance-routines.yml"]
    for name in paths:
        path = host / name
        template = core / name if name.startswith(".github/") else None
        if template is not None and not template.is_file():
            print(f"failed: package template {name}")
            failures += 1
            continue
        if not path.exists() and not path.is_symlink():
            print(f"{'skipped' if portable else 'failed'}: host deployment {name} not installed")
            skipped += int(portable)
            failures += int(not portable)
            continue
        try:
            if template is not None:
                valid = path.read_bytes() == template.read_bytes()
            else:
                config = json.loads(path.read_text(encoding="utf-8"))
                hooks = [(group, hook) for group in config["hooks"]["PreToolUse"] for hook in group["hooks"]
                         if "codex-bash-read-gate" in hook.get("command", "")]
                valid = len(hooks) == 1 and hooks[0][0]["matcher"] == "^Bash$" and hooks[0][1]["timeout"] == 30
            if not valid:
                raise ValueError("invalid_deployment")
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            print(f"failed: invalid host deployment {name}")
            failures += 1
    if failures:
        return 1
    if skipped:
        return 77
    print("✓ host deployment: Codex hook and canonical workflows checked")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(check_host_deployment(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent))
    except (OSError, ValueError, TypeError):
        print("host_deployment_check_failed")
        raise SystemExit(1)
