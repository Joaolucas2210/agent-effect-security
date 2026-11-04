#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# INC-02 closure: `effects` in the MCP registry (integration/mcp_registry.py) and the run-scoped deny of write/network MCP tools in hooks/adf-deny-gate.py.
"$PYTHON" -c 'import tools.pdp, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-mcp-effects.py"
