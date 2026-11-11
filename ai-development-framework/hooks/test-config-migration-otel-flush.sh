#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# Phase 2C (ARCH-09/R-16, ADR 0040): otel_export._flush_seconds reads integration/host_config.py; golden equivalence matrix.
"$PYTHON" -c 'import integration.otel_export, integration.host_config, integration.control_plane_pins' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-config-migration-otel-flush.py"
