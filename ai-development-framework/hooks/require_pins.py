#!/usr/bin/env python3
"""Fail fast when an installed dependency differs from its pin in requirements-test.txt (the single source).

  require_pins.py jsonschema            -> exit 0 if the installed jsonschema equals its pin, else 1 with a fix
  require_pins.py --requirements FILE NAME...

Gates validate closed JSON Schemas; a different validator version is a different gate, so the version is exact.
The pin lives in one file so Dependabot (or a human) bumps it in one place and the whole suite proves it.
"""
import re
import sys
from importlib import metadata
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "requirements-test.txt"
_PIN = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*==\s*([^\s;#]+)")


def pins(requirements):
    found = {}
    for line in Path(requirements).read_text(encoding="utf-8").splitlines():
        match = _PIN.match(line)
        if match:
            found[match.group(1).lower().replace("_", "-")] = match.group(2)
    return found


def check(names, requirements=DEFAULT):
    """-> list of problems; empty means every named package is installed at exactly its pin."""
    declared, problems = pins(requirements), []
    for name in names:
        key = name.lower().replace("_", "-")
        if key not in declared:
            problems.append(f"{name} has no exact pin in {requirements}")
            continue
        try:
            installed = metadata.version(key)
        except metadata.PackageNotFoundError:
            installed = None
        if installed != declared[key]:
            problems.append(f"{name}=={declared[key]} is required (installed: {installed or 'none'})")
    return problems


def main(argv):
    requirements = DEFAULT
    if argv[:1] == ["--requirements"] and len(argv) > 1:
        requirements, argv = Path(argv[1]), argv[2:]
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    problems = check(argv, requirements)
    for problem in problems:
        print(problem)
    if problems:  # the exact remediation lines are part of the contract (test-contracts-v1-dependency.sh)
        print("fix it with: make install-dev")
        print("python -m pip install -r ai-development-framework/requirements-test.txt")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
