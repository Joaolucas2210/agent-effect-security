#!/usr/bin/env bash
# Closed maintenance loops: evidence first; humans approve code-changing work in a PR.
set -euo pipefail

ADF="${ADF:-ai-development-framework}"
DRY_RUN="${DRY_RUN:-1}"
GRAPH_PATH="${GRAPH_PATH:-graphify-out/graph.json}"
JQ="${JQ:-jq}"

usage() {
  echo "usage: maintenance-routine.sh {dead-code|abstractions|security|graph|token-budget|governance}"
}

routine="${1:-}"
case "$routine" in
  dead-code|abstractions|security|graph|token-budget|governance) ;;
  *) usage >&2; exit 2 ;;
esac
case "$DRY_RUN" in 0|1) ;; *) echo "✗ DRY_RUN must be 0 or 1" >&2; exit 2 ;; esac

task="routine-$routine"
record() {
  ADF_DIR="$ADF" TASK="$task" ARCHETYPE=Maintainer PHASE="$routine" TOKENS_IN=na TOKENS_OUT=na \
    BUDGET_REMAINING=na DURATION_SECONDS=na COST_USD=na SWITCHED=false TRIGGER=none \
    OUTCOME="$1" "$ADF/hooks/observability.sh" "$2"
}
finish() {
  local rc=$?
  trap - EXIT
  record "$( [ "$rc" -eq 0 ] && echo success || echo failure )" complete
  exit "$rc"
}
trap finish EXIT

run() { command -v rtk >/dev/null 2>&1 && rtk "$@" || "$@"; }
graph_check() {
  if [ "$DRY_RUN" = 1 ]; then GRAPH_CHECK_NO_REFRESH=1 run make -s graph-check
  else run make -s graph-check; fi
}

record in_progress record
echo "▶ maintenance routine: $routine (dry-run=$DRY_RUN)"
run make -s quality
run make -s mcp-audit
run make -s skill-audit
graph_check

require_graph() {
  [ -f "$GRAPH_PATH" ] || { echo "✗ graph missing: $GRAPH_PATH" >&2; exit 1; }
  command -v "$JQ" >/dev/null 2>&1 || { echo "✗ jq is required for graph evidence" >&2; exit 1; }
}

case "$routine" in
  dead-code)
    require_graph
    echo "▶ candidates with no incoming graph call (suggest-only; tests/entry points need human review)"
    "$JQ" -r '
      [.links[]? | select(.relation == "calls") | .target] as $called |
      [.nodes[] | select(._callable == true) |
       select(.id as $id | $called | index($id) | not) |
       select(.source_file | test("(^|/)(test|tests|fixtures)/") | not) |
       "  \(.source_file):\(.source_location) \(.label)"] | .[]? // empty
    ' "$GRAPH_PATH"
    echo "  No automatic deletion. Open a PR only after callers, tests, and public entry points are reviewed."
    ;;
  abstractions)
    require_graph
    echo "▶ duplicate callable names across files (suggest-only; inspect ownership and boundary leakage)"
    "$JQ" -r '
      [.nodes[] | select(._callable == true) |
       {name: (.norm_label // .label), where: "\(.source_file):\(.source_location) \(.label)"}] |
      sort_by(.name) | group_by(.name)[] | select(length > 1) |
      "  " + .[0].name + "\n" + (map("    " + .where) | join("\n"))
    ' "$GRAPH_PATH"
    echo "  No automatic unification. A human decides whether shared policy belongs behind one boundary."
    ;;
  security)
    echo "▶ tracked-file secret and whitespace sweep"
    run git diff --check
    if run git ls-files | grep -E '(^|/)\.env($|\.)|\.(pem|p12|key)$'; then
      echo "✗ tracked secret-like file detected" >&2
      exit 1
    fi
    if run git grep -n -I -E 'AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY' -- .; then
      echo "✗ secret signature detected in tracked content" >&2
      exit 1
    fi
    echo "✓ no tracked .env/key material"
    ;;
  graph)
    if [ "$DRY_RUN" = 1 ]; then
      echo "  Dry run verified freshness without updating. Use DRY_RUN=0 to let graph-check refresh graphify."
    fi
    ;;
  token-budget)
    run make -s token-budget
    if [ "$DRY_RUN" = 0 ]; then run make -s metrics-snapshot
    else echo "  Dry run did not append metrics. Use DRY_RUN=0 to snapshot this commit."; fi
    ;;
  governance)
    echo "✓ MCP allowlist and skill governance audits completed above"
    ;;
esac
