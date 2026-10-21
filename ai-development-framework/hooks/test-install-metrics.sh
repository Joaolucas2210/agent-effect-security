#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Exercises install-metrics.py and the Makefile install-metrics target, offline.
exec "${ADF_CONTRACTS_PYTHON:-python3}" "$ROOT/hooks/test-install-metrics.py"
