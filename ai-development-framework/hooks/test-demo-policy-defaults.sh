#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# Phase 2A (R-10/ARCH-03): `adf doctor`, `adf hook-snippet` and `adf projects enable` name the read policy in effect (integration/cli.py, hooks/adf-projects.py); exit codes and stdout contracts unchanged.
"$PYTHON" -c 'import jsonschema, integration.cli, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-demo-policy-defaults.py"
