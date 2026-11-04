#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONDONTWRITEBYTECODE=1 "${ADF_CONTRACTS_PYTHON:-python3}" "$ROOT/hooks/test-brand-assets.py"
