#!/usr/bin/env bash
# Self-test for hooks/graph-check.sh: ancestor stamps, squash-merge stamps, code drift, read-only mode.
set -euo pipefail
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/graph-check.sh" --self-test
