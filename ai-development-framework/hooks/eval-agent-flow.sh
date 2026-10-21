#!/usr/bin/env bash
# Agent-flow eval harness (Evaluation-Driven Development — the outer loop).
# Runs a fixture case's objective gate, requires a captured trajectory, and records
# the result. Reproducible without an LLM in the loop: the gate is the truth, the
# trajectory is the evidence of a run.
#
#   resolved = fixture gate passed.  Exit code = resolved (0 yes / 1 no) so this
#   behaves like a gate. Trajectory missing = hard fail (trajectory is first-class).
#   Runtime absent = honest skip (resolved=na, exit 0) — same policy as ci-quality-gates.
#
# Polyglot by the fixture's gate file (stdlib runners only, no new dep):
#   test.js  -> node --test        test_*.py -> python3 -m unittest discover
#
# Usage: eval-agent-flow.sh [CASE]      (default: sum-bug)
#        eval-agent-flow.sh --all       every fixture; exit 1 if any case regressed
set -uo pipefail

ADF="${ADF:-ai-development-framework}"
EVALS="$ADF/docs/evals"
CSV="$EVALS/results.csv"

# Gate runtime, picked by the fixture's gate file. One language per fixture.
detect_lang() {
  if [ -f "$1/test.js" ]; then echo "js node"
  elif ls "$1"/test_*.py >/dev/null 2>&1; then echo "py python3"
  fi
}

run_gate() {
  case "$2" in
    js) ( cd "$1" && node --test test.js ) ;;
    py) ( cd "$1" && python3 -m unittest discover ) ;;
  esac
}

# Append idempotently per commit+case (same dedup rule as metrics-snapshot).
record_row() {
  local row="$1" tmp
  [ "${ADF_EVAL_WRITE:-1}" = 0 ] && return 0
  [ -f "$CSV" ] || echo "date,commit,case,resolved,iterations,est_tokens,gate" > "$CSV"
  tmp="$(mktemp)"; grep -v ",$2,$3," "$CSV" > "$tmp" 2>/dev/null || true; mv "$tmp" "$CSV"
  echo "$row" >> "$CSV"
  echo "✓ recorded: $row"
}

# Same outcome, in the shared event log the Learning Loop reads.
record_event() {
  local outcome=failure
  [ "${ADF_EVAL_WRITE:-1}" = 0 ] && return 0
  [ "$2" = yes ] && outcome=success
  [ "$2" = na ]  && outcome=skipped
  ADF_DIR="$ADF" TASK="eval-$1" ARCHETYPE=Grower PHASE=eval TOKENS_IN=na TOKENS_OUT=na BUDGET_REMAINING=na \
    DURATION_SECONDS="$3" OUTCOME="$outcome" "$ADF/hooks/observability.sh" complete
}

# The verdict: gate passed, gate failed, or no runtime to judge with (never a fake pass).
resolve() {
  if ! command -v "$3" >/dev/null 2>&1; then
    echo "⚠ $3 absent — gate not evaluated (local mode, not a pass)" >&2
    echo "na skipped-no-$3"
  elif run_gate "$1" "$2" >/dev/null 2>&1; then echo "yes pass"
  else echo "no fail"; fi
}

# Trajectory frontmatter (iterations / est_tokens); `na` when absent, never invented.
field() { awk -F': *' -v k="$1" '$1==k{print $2; exit}' "$2"; }

# SECONDS follows the wall clock, which steps backwards on WSL2/VM resync: na, never a negative number.
elapsed() { [ "$((SECONDS - $1))" -ge 0 ] && echo "$((SECONDS - $1))" || echo na; }

# Shared legacy projection; v1 calls this with errexit so write errors cannot pass.
project_case() {
  local case="$1" resolved="$2" gate="$3" iters="$4" tokens="$5" duration="$6"
  local commit date
  commit="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
  date="$(git show -s --format=%cs HEAD 2>/dev/null || echo nodate)"
  if [ "${ADF_EVAL_WRITE:-1}" = 0 ]; then
    echo "↷ eval persistence suppressed"
    return 0
  fi
  record_row "$date,$commit,$case,$resolved,$iters,$tokens,$gate" "$commit" "$case" || return 2
  # A run that is not in the event log did not happen for the Learning Loop: never swallow the write error.
  record_event "$case" "$resolved" "$duration" || { echo "✗ $case: run not recorded in the event log" >&2; return 2; }
}

one_case() {
  if [ "${ADF_EVENTS_V1:-0}" = 1 ]; then
    command -v python3 >/dev/null 2>&1 || { echo "✗ events v1: Python required" >&2; return 2; }
    python3 "$(dirname "${BASH_SOURCE[0]}")/run-events.py" "$1"
    return $?
  fi
  local case="$1" fix="$EVALS/fixtures/$1" traj="$EVALS/runs/$1.trajectory.md" started=$SECONDS
  echo "▶ eval-agent-flow ($case)"
  [ -d "$fix" ]  || { echo "✗ no fixture at $fix"; return 1; }
  [ -f "$traj" ] || { echo "✗ $case: no trajectory at $traj — a run MUST capture reason/act/observe"; return 1; }

  local lang need resolved gate iters tokens
  read -r lang need <<< "$(detect_lang "$fix")"
  [ -n "$lang" ] || { echo "✗ $case: fixture has no gate (expected test.js or test_*.py)"; return 1; }

  iters="$(field iterations "$traj")";  [ -n "$iters" ] || iters=na
  tokens="$(field est_tokens "$traj")"; [ -n "$tokens" ] || tokens=na

  read -r resolved gate <<< "$(resolve "$fix" "$lang" "$need")"

  project_case "$case" "$resolved" "$gate" "$iters" "$tokens" "$(elapsed "$started")" || return 2
  [ "$resolved" = yes ] || [ "$resolved" = na ]   # exit code = resolved
}

all_cases() {
  if [ "${ADF_EVENTS_V1:-0}" = 1 ] && [ "${RUN_ID+x}" = x ]; then
    echo "✗ events v1: omit RUN_ID for --all (one generated ID per case)" >&2
    return 2
  fi
  local rc=0 d c
  for d in "$EVALS"/fixtures/*/; do
    [ -d "$d" ] || continue
    c="$(basename "$d")"
    one_case "$c" || { local status=$?; [ "$status" -le "$rc" ] || rc=$status; }
  done
  if [ "${ADF_EVAL_WRITE:-1}" = 0 ]; then
    echo "▶ all cases run — eval persistence suppressed"
  else
    echo "▶ all cases run (see $CSV) — next: make learn"
  fi
  return "$rc"
}

# Sourcing exposes only the existing gate/projection functions to the v1 writer.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  if [ "${ADF_EVAL_WRITE:-1}" = 0 ] && [ "${ADF_EVENTS_V1:-0}" = 1 ]; then
    echo "✗ eval_persistence_disabled" >&2
    exit 2
  fi
  case "${1:-sum-bug}" in
    --all) all_cases ;;
    *)     one_case "${1:-sum-bug}" ;;
  esac
fi
