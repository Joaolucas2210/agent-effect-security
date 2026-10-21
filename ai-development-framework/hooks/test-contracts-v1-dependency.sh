#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

python3 -m venv "$tmp/venv"
set +e
ADF_CONTRACTS_PYTHON="$tmp/venv/bin/python" "$ROOT/hooks/test-contracts-v1.sh" >"$tmp/stdout" 2>"$tmp/stderr"
rc=$?
set -e
output="$(cat "$tmp/stdout" "$tmp/stderr")"
[ "$rc" -ne 0 ]
grep -q 'jsonschema' <<< "$output"
grep -Fxq 'python -m pip install -r ai-development-framework/requirements-test.txt' <<< "$output"
! grep -q 'Traceback (most recent call last):' <<< "$output"
echo "missing jsonschema self-test: passed (internal exit code: $rc)"
