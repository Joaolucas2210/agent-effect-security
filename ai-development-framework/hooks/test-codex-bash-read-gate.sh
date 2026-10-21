#!/usr/bin/env bash
set -euo pipefail
# Exercises codex-bash-read-gate.py and codex-bash-read-gate.wrapper.sh via the project hooks.json command.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
exec "$PYTHON" "$ROOT/hooks/test-codex-bash-read-gate.py"
