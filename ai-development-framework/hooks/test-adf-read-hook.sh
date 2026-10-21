#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# REQ-MP-01: exercises hooks/adf-read-hook.py as a real hook process (stdin JSON, CLAUDE_PROJECT_DIR) over the Claude Read gate.
"$PYTHON" "$ROOT/hooks/require_pins.py" jsonschema || exit 1
"$PYTHON" -c 'import tools.pdp, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-adf-read-hook.py"
