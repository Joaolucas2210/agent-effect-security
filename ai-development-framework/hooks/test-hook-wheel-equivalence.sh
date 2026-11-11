#!/usr/bin/env bash
# R-13 / Phase 2C: the wheel's `adf hook` decides exactly like the clone (allow, deny, evidence, pins, NOT PROTECTED).
# Everything under TMPDIR; missing tooling prints SKIPPED (exit 77; ADF_PACKAGING_REQUIRED=1 fails).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-hook-wheel-equivalence.py"
