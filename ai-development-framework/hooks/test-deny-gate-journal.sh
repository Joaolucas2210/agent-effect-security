#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# ADR 0028 slice 1c: journal for deny-only and pre-gate denies, run-scoped network deny; hooks/adf-deny-gate.py, hooks/adf-read-hook.py, integration/adapter_attempt.py, hooks/adf-projects.py.
"$PYTHON" -c 'import tools.pdp, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-deny-gate-journal.py"
