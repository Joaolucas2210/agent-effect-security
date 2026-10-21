#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# REQ-MP-02: exercises hooks/adf-projects.py (list/enable/disable/reasons) against the rules of hooks/adf-read-hook.py.
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-adf-projects.py"
