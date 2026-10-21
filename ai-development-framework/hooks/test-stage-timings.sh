#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
"$PYTHON" -c 'import integration.local_read_adapter' >/dev/null 2>&1 || { echo "run: make install-dev"; exit 1; }
exec "$PYTHON" "$ROOT/hooks/test-stage-timings.py"
