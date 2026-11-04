#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# ADR 0031 slice 2: server definitions and tool-list digests in integration/mcp_registry.py, hooks/adf-deny-gate.py, integration/cli.py.
"$PYTHON" -c 'import tools.pdp, integration.local_read_adapter, mcp.client.stdio' >/dev/null 2>&1 || { echo "skipped: control-plane packages or mcp client not importable — run: make install-dev"; exit 0; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-mcp-registry-2.py"
