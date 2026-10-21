#!/usr/bin/env bash
# learn.sh self-check: aggregation, recurrence rule, confidence, filename safety,
# and the invariant that matters most — a human-edited proposal is never clobbered.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
adf="$tmp/framework"
events="$adf/docs/observability/events.jsonl"
props="$adf/docs/traces/proposals"
mkdir -p "$(dirname "$events")" "$props"

ev() { printf '{"timestamp":"%s","task":"%s","archetype":"Maintainer","phase":"%s","outcome":"%s"}\n' "$1" "$2" "$3" "$4" >> "$events"; }
# recurring: same task, two distinct days. single-day: one task, two events same day.
ev 2026-08-01T10:00:00Z gate-mutation-mutmut quality-gate failure
ev 2026-08-02T10:00:00Z gate-mutation-mutmut quality-gate failure
ev 2026-08-03T10:00:00Z routine-dead-code dead-code failure
ev 2026-08-03T11:00:00Z routine-dead-code dead-code failure
ev 2026-08-04T10:00:00Z gate-tests-npm quality-gate success
ev 2026-08-05T10:00:00Z ../../escape quality-gate failure
# starts alphanumeric (passes the prefix guard) but is a path — the traversal case
ev 2026-08-06T10:00:00Z evil/../../escape quality-gate failure

out="$(ADF="$adf" "$ROOT/hooks/learn.sh")"

[[ "$out" == *"RECURRING x2 days"* ]]                 # two distinct days → recurring
[[ "$out" == *"routine-dead-code"* ]]                 # two same-day events → listed
[[ "$out" != *"RECURRING x2 days] → last 2026-08-03"* ]]
[[ "$out" != *"gate-tests-npm"* ]]                    # success is not a failure
[[ "$out" == *"unsafe task name"* ]]                  # path-like task rejected
[ "$(grep -c "unsafe task name" <<< "$out")" = 2 ]   # both the prefix and the traversal case
[ ! -e "$props/../../escape.md" ] && [ ! -f "$tmp/escape.md" ]
[ ! -e "$adf/docs/escape.md" ] && [ ! -e "$tmp/escape.md" ]
grep -q '^\*\*medium\*\*' "$props/gate-mutation-mutmut.md"   # recurring → medium
grep -q '^\*\*low\*\*'    "$props/routine-dead-code.md"      # single day → low
grep -q '^## Expected impact' "$props/gate-mutation-mutmut.md"
grep -q 'quality-thresholds' "$props/gate-mutation-mutmut.md"   # gate → threshold target
grep -q 'maintenance-routine' "$props/routine-dead-code.md"     # routine → hook target

# never clobber a human proposal
echo "HUMAN EDIT" > "$props/gate-mutation-mutmut.md"
out2="$(ADF="$adf" "$ROOT/hooks/learn.sh")"
[[ "$out2" == *"left untouched"* ]]
[ "$(cat "$props/gate-mutation-mutmut.md")" = "HUMAN EDIT" ]

# no events → clean exit, no proposals invented
rm -f "$events"
[[ "$(ADF="$adf" "$ROOT/hooks/learn.sh")" == *"nothing recorded yet"* ]]

echo "✓ learn self-test"
