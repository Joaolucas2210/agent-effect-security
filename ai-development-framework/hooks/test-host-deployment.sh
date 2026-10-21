#!/usr/bin/env bash
set -euo pipefail
# Exercises check-host-deployment.py: clone failures, portable skips and invalid deployments.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${ADF_CONTRACTS_PYTHON:-python3}" "$ROOT/hooks/test-host-deployment.py"
