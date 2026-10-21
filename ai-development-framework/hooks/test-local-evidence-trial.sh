#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# Exercises run-local-evidence-trial.py (P2): fixed suite, ingest of persisted bundles, redaction.
"$PYTHON" "$ROOT/hooks/require_pins.py" jsonschema || exit 1
"$PYTHON" -c 'import tools.pdp, runtime.pep, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
exec "$PYTHON" "$ROOT/hooks/test-local-evidence-trial.py"
