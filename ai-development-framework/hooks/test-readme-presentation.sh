#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ADF_CONTRACTS_PYTHON:-python3}"
# Presentation gate: hooks/readme_check.py over README.md / README.pt-BR.md and docs/assets/brand, plus its negative fixtures.
PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" "$ROOT/hooks/test-readme-presentation.py"
