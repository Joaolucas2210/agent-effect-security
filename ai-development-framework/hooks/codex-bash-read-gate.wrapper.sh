#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
export ADF_TRUSTED_REPOSITORY="${ADF_TRUSTED_REPOSITORY:-$ROOT}"
export ADF_TRUSTED_REVISION="${ADF_TRUSTED_REVISION:-HEAD}"
export ADF_EVIDENCE_DIR="${ADF_EVIDENCE_DIR:-$ROOT/ai-development-framework/docs/observability/evidence}"
exec "$ROOT/.venv/bin/python3" "$SCRIPT_DIR/codex-bash-read-gate.py"
