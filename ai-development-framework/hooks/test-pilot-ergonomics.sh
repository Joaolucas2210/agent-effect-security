#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# Pilot follow-ups 1-3: labels in the tamper deny (hooks/adf-read-hook.py), host env from the registration and clone line in `adf doctor` (integration/control_plane_pins.py, integration/cli.py), key export in `adf hook-snippet` (integration/cli.py).
"$PYTHON" -c 'import tools.pdp, integration.local_read_adapter' >/dev/null 2>&1 || { echo "control-plane packages not importable — run: make install-dev"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-pilot-ergonomics.py"
