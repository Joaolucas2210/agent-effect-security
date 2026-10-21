#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# `adf` entry point (integration/cli.py): dispatch to hooks/adf-projects.py, hooks/adf-read-hook.py, the policy pack and the A2A gateway.
"$PYTHON" -c 'import jsonschema, integration.cli' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
cd "$ROOT" && PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-adf-cli.py"
