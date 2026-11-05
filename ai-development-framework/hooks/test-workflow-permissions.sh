#!/usr/bin/env bash
# Contract: quality gates (ci.yml) never get write scopes, and every write automation is inert
# unless the owner sets ADF_AGENTIC_AUTOMATION=true. Reads the canonical templates.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WF="$ROOT/.github/workflows"

python3 - "$WF" <<'EOF'
import re, sys
from pathlib import Path

wf = Path(sys.argv[1])
ci = (wf / "ci.yml").read_text()
# ponytail: line scan, not a YAML parser — the templates are ours and use block style only.
assert not re.search(r":\s*write\b", ci), "ci.yml must not grant any write permission"
assert re.search(r"(?m)^permissions:\n  contents: read$", ci), "ci.yml needs top-level contents: read"
assert "secrets." not in ci, "ci.yml must not read repository secrets"

auto = (wf / "agentic-automation.yml").read_text()
assert re.search(r"(?m)^permissions: \{\}$", auto), "agentic-automation.yml needs top-level permissions: {}"
jobs = re.split(r"(?m)^  (?=[a-z-]+:$)", auto.split("\njobs:\n", 1)[1])[1:]
assert jobs, "agentic-automation.yml has no jobs"
for job in jobs:
    name = job.split(":", 1)[0]
    cond = re.search(r"    if: >-\n((?:      .*\n)+)", job)
    assert cond, f"{name}: missing if"
    # The opt-in must be ANDed with the whole remaining condition, never one side of an ||.
    body = " ".join(cond.group(1).split())
    assert body.startswith("vars.ADF_AGENTIC_AUTOMATION == 'true' && ("), f"{name}: opt-in not guarding the whole condition"
    assert body.endswith(")"), f"{name}: unbalanced opt-in guard"

post = (wf / "post-observability.yml").read_text()
assert "workflows: [ci]" in post and "head -n 1" in post, "post-observability must follow ci and post one line"
assert "actions/checkout" not in post, "post-observability must never check out PR code"
print("✓ workflow permissions: ci read-only, write automations opt-in, trusted poster")
EOF
