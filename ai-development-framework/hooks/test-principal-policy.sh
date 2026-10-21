#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# ADR 0024: principal_rules in the pinned host policy (tools/pdp.py, policy-packs/effect-security-read-v0/build.py).
"$PYTHON" -c 'import jsonschema' >/dev/null 2>&1 || { echo "jsonschema is required — run: make install-dev"; exit 1; }
cd "$ROOT" && PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-principal-policy.py"
