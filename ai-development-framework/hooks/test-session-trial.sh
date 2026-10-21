#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# Exercises run-session-trial.py through test-session-trial.py, including redacted CLI failures.
"$PYTHON" -c 'import jsonschema, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
exec "$PYTHON" "$ROOT/hooks/test-session-trial.py"
