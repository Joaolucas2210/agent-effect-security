#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

ADF_DIR="$tmp/framework" TASK=feature-42 ARCHETYPE=Builder PHASE=build \
  TOKENS_IN=120 TOKENS_OUT=80 BUDGET_REMAINING=800 DURATION_SECONDS=4 COST_USD=0.001 \
  "$ROOT/hooks/observability.sh" record >/dev/null
ADF_DIR="$tmp/framework" TASK=feature-42 ARCHETYPE=Maintainer PHASE=handoff SWITCHED=true \
  TRIGGER=security-risk TOKENS_IN=20 TOKENS_OUT=10 BUDGET_REMAINING=500 DURATION_SECONDS=2 \
  OUTCOME=success "$ROOT/hooks/observability.sh" complete >/dev/null
ADF_DIR="$tmp/framework" TASK=unknown-43 ARCHETYPE=Builder PHASE=build \
  "$ROOT/hooks/observability.sh" record >/dev/null

events="$tmp/framework/docs/observability/events.jsonl"
trajectory="$tmp/framework/docs/observability/trajectories/feature-42.trajectory.md"
[ "$(wc -l < "$events" | tr -d ' ')" = 3 ]
grep -q '"switched":true' "$events"
grep -q '"tokens_in":null' "$events"
grep -q 'Trajectory — feature-42' "$trajectory"
summary="$(ADF_DIR="$tmp/framework" "$ROOT/hooks/observability.sh" summary)"
[[ "$summary" == *"events=3"* && "$summary" == *"switches=1"* && "$summary" == *"tokens=230"* ]]
if ADF_DIR="$tmp/framework" TASK=../../escape "$ROOT/hooks/observability.sh" complete >/dev/null 2>&1; then
  echo "✗ observability accepted a path-like TASK" >&2
  exit 1
fi
echo "✓ observability self-test"
