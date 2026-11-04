#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# ADR 0028 slice 1b: the Bash read-equivalent grammar in hooks/adf-deny-gate.py, routed by hooks/adf-read-hook.py after hooks/codex-bash-read-gate.py.
"$PYTHON" -c 'import tools.pdp, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-bash-read-grammar.py"
