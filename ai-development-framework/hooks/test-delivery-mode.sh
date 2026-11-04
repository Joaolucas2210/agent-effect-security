#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# ADR 0029: delivery_mode in integration/local_evidence_bundle.py, local_read_adapter.py, read_gate_host.py, mcp_read_server.py, a2a_gateway.py, cli.py; hooks/claude-code-read-gate.py via adf-read-hook.py.
"$PYTHON" -c 'import tools.pdp, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-delivery-mode.py"
