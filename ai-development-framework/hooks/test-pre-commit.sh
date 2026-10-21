#!/usr/bin/env bash
# pre-commit self-check: the cheap local gate must actually block a bad staged change,
# and must stay silent about the expensive gates it deliberately leaves to CI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
fw="$tmp/ai-development-framework"; mkdir -p "$fw/hooks" "$fw/rules"
for h in pre-commit shell-complexity.sh shell-complexity.awk thresholds.sh; do cp "$ROOT/hooks/$h" "$fw/hooks/"; done
cp "$ROOT/rules/quality-thresholds.md" "$fw/rules/"
( cd "$tmp" && git init -q . && git config user.email t@t && git config user.name t )
# Minimal PATH: this exercises the hook itself, not whatever optional tools the host has.
hook() { ( cd "$tmp" && PATH=/usr/bin:/bin ai-development-framework/hooks/pre-commit 2>&1 ); }

# Nothing staged: nothing to measure, and the hook says so instead of claiming a pass.
out="$(hook)"; grep -q 'pre-commit gates passed' <<< "$out"
grep -q 'run in CI' <<< "$out"

# A staged shell file over the threshold blocks the commit.
{ echo 'bad() {'; for i in $(seq 1 12); do echo "  [ -f $i ] && echo $i"; done; echo '}'; echo bad; } > "$tmp/bad.sh"
( cd "$tmp" && git add bad.sh )
out="$(hook)" && { echo "✗ pre-commit let an over-complex file through" >&2; exit 1; }
grep -q 'shell complexity gate failed' <<< "$out"

# ...and a clean one passes. Staged-only: an untracked mess must not block an unrelated commit.
printf 'ok_fn() {\n  echo fine\n}\nok_fn\n' > "$tmp/bad.sh"
hook | grep -q 'pre-commit gates passed'
{ echo 'worse() {'; for i in $(seq 1 20); do echo "  [ -f $i ] && echo $i"; done; echo '}'; } > "$tmp/unstaged.sh"
hook | grep -q 'pre-commit gates passed'

echo "✓ pre-commit self-test"
