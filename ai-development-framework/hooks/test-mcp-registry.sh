#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# ADR 0031 slice 1: integration/mcp_registry.py through hooks/adf-deny-gate.py and hooks/adf-read-hook.py as a real hook process.
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-mcp-registry.py"
