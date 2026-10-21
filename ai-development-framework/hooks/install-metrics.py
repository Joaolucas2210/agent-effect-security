#!/usr/bin/env python3
"""Copy local metrics/trial tooling, preserving host files and excluding captured data."""
import os
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[2]
IGNORES = shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info", ".env*", ".venv", "node_modules", "build", "dist")
CAPTURES = ("events.jsonl", "evidence", "trials", "runs", "trajectories")


def ignore_captures(directory, names):
    ignored = set(IGNORES(directory, names))
    relative = Path(directory).relative_to(ROOT / "ai-development-framework")
    if relative == Path("docs/observability"):
        ignored.update(CAPTURES)
    if relative == Path("docs/metrics"):
        ignored.update(name for name in names if name != "history.csv" and not name.endswith(".md"))
    if relative == Path("docs/traces/proposals"):
        ignored.update(name for name in names if name != "TEMPLATE.md")
    if relative == Path("docs/traces"):
        ignored.update(name for name in names if name not in ("README.md", "proposals"))
    if relative == Path("docs/evals/runs"):
        ignored.update(name for name in names if name not in ("sum-bug.trajectory.md", "median-bug.trajectory.md"))
    return ignored


def install(destination):
    dest = Path(destination).resolve(strict=True)
    if not dest.is_dir() or dest.is_relative_to(ROOT) or ROOT.is_relative_to(dest):
        raise ValueError("DEST must be a separate project directory")
    core, runner = dest / "ai-development-framework", dest / "Makefile.adf"
    if any(path.exists() or path.is_symlink() for path in (core, runner)):
        raise ValueError("installation already exists; no files were replaced")
    shutil.copytree(ROOT / "ai-development-framework", core, ignore=ignore_captures)
    for name in ("agent-development-harness.md", "p0d-trial-sessions.md"):
        spec = ROOT / "ai-development-framework/docs/specs" / name
        if not spec.is_file():
            spec = ROOT / "docs/specs" / name
        if spec.is_file():
            (core / "docs/specs").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(spec, core / "docs/specs" / name)
    for name in ("docs/metrics/history.csv", "docs/evals/results.csv"):
        path = core / name
        if path.exists():
            path.write_text(path.read_text().splitlines()[0] + "\n")
    for name in ("LICENSE", "VERSION"):
        source = ROOT / "ai-development-framework" / name
        shutil.copyfile(source if source.exists() else ROOT / name, core / name)
    (core / ".gitignore").write_text("__pycache__/\n*.pyc\n*.egg-info/\n.env*\n" + "".join(f"docs/observability/{name}\n" for name in CAPTURES))
    # Exclusive creation also refuses a runner created after the initial conflict check.
    with runner.open("x") as handle:
        source = ROOT / "Makefile.adf"
        handle.write((source if source.exists() else ROOT / "Makefile").read_text())
    print("✓ installed; host Makefile, AGENTS.md, license and agent settings preserved")
    print("Next in the destination: make -f Makefile.adf install-dev; see docs/trials.md")


if __name__ == "__main__":
    try:
        destination = os.environ.get("DEST")
        if not destination:
            raise ValueError("DEST required: make install-metrics DEST=/your/project")
        install(destination)
    except (OSError, ValueError) as exc:
        print(f"✗ install-metrics: {exc}")
        raise SystemExit(1)
