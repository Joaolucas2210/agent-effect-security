#!/usr/bin/env bash
set -euo pipefail
# Covers integration/task_evaluation.py; no runner or shell execution of assessments.
hook_dir="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$hook_dir/..${PYTHONPATH:+:$PYTHONPATH}"
"${ADF_CONTRACTS_PYTHON:-python3}" "$hook_dir/test-task-evaluation.py"
