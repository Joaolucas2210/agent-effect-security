#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# ADR 0039 (Proposed): the PolicySource seam (integration/extensions.py) is byte-equivalent by default and cannot bypass PDP/PEP, R-09, evidence or signing.
"$PYTHON" -c 'import jsonschema, integration.extensions, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-extension-contracts.py"
