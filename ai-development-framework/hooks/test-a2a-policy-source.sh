#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# ADR 0039 (Proposed) at the A2A edge: one pinned policy load through PolicySource; None or off-contract refuses, never the demo.
"$PYTHON" -c 'import jsonschema, integration.extensions, integration.a2a_gateway' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-a2a-policy-source.py"
