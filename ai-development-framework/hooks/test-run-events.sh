#!/usr/bin/env bash
# H1-01 contracts: run-events.py + eval-agent-flow.sh, including legacy projection.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$ROOT/test-run-events.py"
