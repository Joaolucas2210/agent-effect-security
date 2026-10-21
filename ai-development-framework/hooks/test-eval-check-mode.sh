#!/usr/bin/env bash
# Check mode must evaluate without changing durable eval evidence.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"
MAKEFILE="$REPO/Makefile"
[ ! -f "$REPO/Makefile.adf" ] || MAKEFILE="$REPO/Makefile.adf"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
fw="$tmp/fw"

require() {
  command -v "$1" >/dev/null 2>&1 && return 0
  echo "skipped: $1 unavailable (not green evidence)" >&2
  exit 1
}
run() {
  local label="$1"; shift
  if ( cd "$tmp" && "$@" ) >"$tmp/$label.out" 2>&1; then
    echo "executed: $label"
  else
    echo "failed: $label" >&2
    cat "$tmp/$label.out" >&2
    exit 1
  fi
}
snapshot() {
  local path
  for path in "$fw/docs/evals/results.csv" "$fw/docs/observability" "$fw/docs/traces"; do
    [ -e "$path" ] || { echo "missing:$path"; continue; }
    find "$path" -type f -exec sha256sum {} \; | LC_ALL=C sort
  done
}

require make
require git
require node
require python3
require sha256sum

mkdir -p "$fw/docs" "$fw/hooks" "$fw/rules"
cp -R "$ROOT/docs/evals" "$fw/docs/"
cp -R "$ROOT/docs/traces" "$fw/docs/"
for hook in ci-quality-gates.sh eval-agent-flow.sh eval-required.sh eval-diagnose.sh observability.sh thresholds.sh shell-complexity.sh shell-complexity.awk check-host-deployment.py; do
  cp "$ROOT/hooks/$hook" "$fw/hooks/"
done
cp "$ROOT/rules/quality-thresholds.md" "$fw/rules/"
mkdir -p "$fw/.github/workflows"
cp "$ROOT/.github/workflows/quality-gates.yml" "$ROOT/.github/workflows/maintenance-routines.yml" "$fw/.github/workflows/"
printf '# portable gate fixture\n' > "$tmp/Makefile.adf"
( cd "$tmp" && git init -q && git config user.email test@example.invalid && git config user.name 'Eval Check Test' && git add fw && git commit -q -m init )

before="$(snapshot)"
run eval-check make -s -f "$MAKEFILE" ADF=fw eval-check
[ "$(snapshot)" = "$before" ] || { echo "failed: eval-check changed durable evidence" >&2; exit 1; }
run quality-check make -s -f "$MAKEFILE" ADF=fw quality-check
[ "$(snapshot)" = "$before" ] || { echo "failed: quality-check changed durable evidence" >&2; exit 1; }

if ( cd "$tmp" && ADF_EVENTS_V1=1 ADF_EVAL_WRITE=0 make -s -f "$MAKEFILE" ADF=fw eval-check ) >"$tmp/events.out" 2>&1; then
  echo "failed: events v1 bypassed check mode" >&2
  exit 1
fi
grep -qx '✗ eval_persistence_disabled' "$tmp/events.out" || { echo "failed: missing eval_persistence_disabled" >&2; exit 1; }
[ "$(snapshot)" = "$before" ] || { echo "failed: events v1 wrote durable evidence" >&2; exit 1; }

run eval-write env ADF_EVAL_WRITE=1 make -s -f "$MAKEFILE" ADF=fw eval
[ "$(snapshot)" != "$before" ] || { echo "failed: normal eval stopped writing" >&2; exit 1; }
[ -s "$fw/docs/observability/events.jsonl" ] || { echo "failed: normal eval omitted event" >&2; exit 1; }

echo "✓ eval check mode self-test"
