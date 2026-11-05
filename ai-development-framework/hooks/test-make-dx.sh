#!/usr/bin/env bash
# Contract for the developer entry points in the root Makefile: `make help` lists only targets that exist,
# and the interpreter is the clone's .venv when present, unless ADF_CONTRACTS_PYTHON is set explicitly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MK="$ROOT/Makefile"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

for list in PRODUCT_TARGETS CONTRIB_TARGETS; do
  targets="$(sed -n "s/^$list := //p" "$MK")"
  [ -n "$targets" ] || { echo "failed: $list missing" >&2; exit 1; }
  for t in $targets; do
    grep -qE "^$t:.*## " "$MK" || { echo "failed: make help lists '$t', which has no '## ' description" >&2; exit 1; }
  done
done
listed="$(make -s -f "$MK" help | grep -c '^  ')"
[ "$listed" -ge 10 ] || { echo "failed: make help listed $listed targets" >&2; exit 1; }

show() { (cd "$tmp" && env -u ADF_CONTRACTS_PYTHON "$@" make -s -f "$MK" --eval 'show-py: ; @echo "$$ADF_CONTRACTS_PYTHON"' show-py); }
[ "$(show)" = python3 ] || { echo "failed: without .venv the default must be python3" >&2; exit 1; }
mkdir -p "$tmp/.venv/bin" && printf '#!/bin/sh\n' > "$tmp/.venv/bin/python3" && chmod +x "$tmp/.venv/bin/python3"
[ "$(show)" = "$tmp/.venv/bin/python3" ] || { echo "failed: .venv/bin/python3 was not picked up" >&2; exit 1; }
[ "$(show ADF_CONTRACTS_PYTHON=/opt/py)" = /opt/py ] || { echo "failed: an explicit ADF_CONTRACTS_PYTHON must win" >&2; exit 1; }

echo "✓ make DX: help lists real targets; .venv auto-detected; explicit interpreter wins"
