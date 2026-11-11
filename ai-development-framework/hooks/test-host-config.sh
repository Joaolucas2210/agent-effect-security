#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# Phase 2B (ARCH-09/R-16): integration/host_config.py reproduces every product ADF_* reader; pure, frozen, secrets redacted.
"$PYTHON" -c 'import jsonschema, integration.cli, integration.host_config' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-host-config.py"
