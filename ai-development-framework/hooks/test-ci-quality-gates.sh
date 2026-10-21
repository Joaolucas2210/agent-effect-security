#!/usr/bin/env bash
# ci-quality-gates.sh self-check. The one invariant worth more than all the others:
# **it must never print green for gates that never ran.** Plus: a failing gate blocks
# AND feeds the learning loop.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
fw="$tmp/fw"; mkdir -p "$fw/hooks" "$fw/rules"
# Only the hooks under test — no test-*.sh, so the contract loop can't recurse into this file.
for h in thresholds.sh shell-complexity.sh shell-complexity.awk observability.sh eval-agent-flow.sh eval-required.sh check-host-deployment.py; do
  cp "$ROOT/hooks/$h" "$fw/hooks/"
done
cp "$ROOT/rules/quality-thresholds.md" "$fw/rules/"
mkdir -p "$fw/.github/workflows"
cp "$ROOT/.github/workflows/quality-gates.yml" "$ROOT/.github/workflows/maintenance-routines.yml" "$fw/.github/workflows/"
printf '# portable gate fixture\n' > "$tmp/Makefile.adf"
( cd "$tmp" && git init -q . && git config user.email t@t && git config user.name t )
# GitHub Actions exports CI=true globally. Each scenario must choose its own mode,
# otherwise the local-mode assertion below accidentally inherits the runner's CI mode.
gates() { ( cd "$tmp" && ADF=fw ADF_EVAL_WRITE=1 CI="$1" "$ROOT/hooks/ci-quality-gates.sh" 2>&1 ); }

# 1. Nothing to measure + CI → hard failure. A green CI run with zero gates is the lie this prevents.
out="$(gates 1)" && { echo "✗ CI passed with zero gates evaluated" >&2; exit 1; }
grep -q 'no quality gates evaluated' <<< "$out"

# 2. Same situation locally: allowed to exit 0, but must say it is NOT a pass.
out="$(gates '')"
grep -q 'local mode, not a pass' <<< "$out"
grep -q '✓ .* gate(s) green' <<< "$out" && { echo "✗ claimed green with zero gates" >&2; exit 1; }

# 3. A shell file over the complexity threshold blocks the merge...
{ echo 'bad() {'; for i in $(seq 1 12); do echo "  [ -f $i ] && echo $i"; done; echo '}'; echo bad; } > "$tmp/bad.sh"
( cd "$tmp" && git add bad.sh )
out="$(gates 1)" && { echo "✗ over-threshold shell passed" >&2; exit 1; }
grep -q 'complexity (shell' <<< "$out"
# ...and the failure reaches the learning loop as a recorded signal.
grep -q '"task":"gate-complexity-shell' "$fw/docs/observability/events.jsonl"

# 4. Clean shell = a real, counted gate. Shell is no longer an unmeasured stack.
printf 'ok_fn() {\n  echo fine\n}\nok_fn\n' > "$tmp/bad.sh"
out="$(gates 1)"
grep -q '✓ 1 gate(s) green' <<< "$out"
grep -q 'skipped: evals (no fixtures)' <<< "$out"
grep -q 'skipped: host deployment checks' <<< "$out"

# 5. A failed package self-test still blocks, even when host deployment is absent.
printf 'exit 1\n' > "$fw/hooks/test-broken.sh"
out="$(gates 1)" && { echo "✗ failed contract was skipped" >&2; exit 1; }
grep -q 'contract: test-broken.sh' <<< "$out"

echo "✓ ci-quality-gates self-test"
