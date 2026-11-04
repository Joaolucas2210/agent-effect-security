#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# ADR 0028 slice 1a: exercises hooks/adf-deny-gate.py through hooks/adf-read-hook.py as a real hook process.
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-adf-deny-gate.py"
