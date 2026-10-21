#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# Exercises hooks/run-a2a-live-trial.py over real loopback HTTP (hermetic fixture, in-memory HS256 secret).
"$PYTHON" "$ROOT/hooks/require_pins.py" jsonschema || exit 1
"$PYTHON" -c 'import tools.pdp, integration.a2a_gateway' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-a2a-live-trial.py"
