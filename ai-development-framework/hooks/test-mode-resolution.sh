#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
"$PYTHON" "$ROOT/hooks/require_pins.py" jsonschema || exit 1
exec "$PYTHON" "$ROOT/hooks/test-mode-resolution.py"
