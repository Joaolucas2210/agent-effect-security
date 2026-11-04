#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# ADR 0036: path rule 1.1 in tools/pdp.py and tools/v1/schemas/list-files-input.schema.json; sensitive-path-policy-v2 in runtime/v1/policies, loaded by integration/local_read_adapter.py, hooks/adf-deny-gate.py, hooks/codex-bash-read-gate.py and policy-packs/effect-security-read-v0/build.py.
"$PYTHON" -c 'import tools.pdp, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-root-dotfiles.py"
