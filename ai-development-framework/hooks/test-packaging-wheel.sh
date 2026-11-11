#!/usr/bin/env bash
# R-13: sdist + wheel build offline, metadata/contents check, non-editable install smoke, uninstall. Nothing written
# in the repo or the project venv (all under TMPDIR). Missing tooling prints SKIPPED (exit 77; ADF_PACKAGING_REQUIRED=1 fails).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-packaging-wheel.py"
