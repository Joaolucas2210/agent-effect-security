#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# Phase 2C (ARCH-09/R-16, ADR 0040 Phase 2C notes): pins today's behaviour of the four open config issues (OI-1..OI-4).
"$PYTHON" -c 'import jsonschema, integration.cli, integration.host_config, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-config-migration-open-issues.py"
