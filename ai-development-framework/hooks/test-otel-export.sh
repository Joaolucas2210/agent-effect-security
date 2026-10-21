#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
"$PYTHON" -c 'import integration.otel_export, integration.a2a_gateway' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
exec "$PYTHON" "$ROOT/hooks/test-otel-export.py"
