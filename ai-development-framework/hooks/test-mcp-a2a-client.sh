#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# Host-side A2A client (integration/mcp_a2a_client.py): the model gets read_via_adf(path), never the bearer.
"$PYTHON" -c 'import mcp, jsonschema' >/dev/null 2>&1 || { echo "~ mcp-a2a-client self-test skipped (run: make install-dev)"; exit 0; }
cd "$ROOT" && PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-mcp-a2a-client.py"
