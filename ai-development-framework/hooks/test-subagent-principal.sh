#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# ADR 0033: act chain in integration/read_gate_host.py, max_act_depth in tools/pdp.py and tools/v1/schemas/policy-bundle.schema.json, builder policy-packs/effect-security-read-v0/build.py, journal integration/adapter_attempt.py, spans hooks/claude-code-read-gate.py.
"$PYTHON" -c 'import tools.pdp, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-subagent-principal.py"
