#!/usr/bin/env bash
# CI quality gates: the full metric wall. Any failing number blocks the merge.
# Gates run only for a DETECTED stack; anything skipped is REPORTED, never counted as green.
# Thresholds come from rules/quality-thresholds.md (hooks/thresholds.sh reads them).
# ponytail: detection over config — add a stack by adding one gate_<stack> function.
set -euo pipefail

ADF="${ADF:-ai-development-framework}"
# shellcheck source=thresholds.sh
. "$(dirname "${BASH_SOURCE[0]}")/thresholds.sh"
COV="$(threshold coverage 80)"; CCN="$(threshold complexity 10)"; LEN="$(threshold size 50)"

run()  { command -v rtk >/dev/null 2>&1 && rtk "$@" || "$@"; }
have() { command -v "$1" >/dev/null 2>&1; }

# A failing gate is the learning loop's input, so record it before dying. `|| true`:
# a recording problem must never mask the gate failure it was describing.
record_failure() {
  local slug
  [ "${ADF_EVAL_WRITE:-1}" = 0 ] && return 0
  # ponytail: 40-char cap keeps the proposal filename sane. The message is fixed per
  # call site, so the truncated slug is still a stable recurrence key.
  slug="gate-$(printf '%s' "$1" | tr -cs 'A-Za-z0-9' '-' | cut -c1-40 | sed 's/-*$//')"
  ADF_DIR="$ADF" TASK="$slug" ARCHETYPE=Maintainer PHASE=quality-gate OUTCOME=failure \
    "$ADF/hooks/observability.sh" record >/dev/null 2>&1 || true
}
fail() { echo "✗ $1"; record_failure "$1"; exit 1; }

CI="${CI:-}"                     # set CI=1 (any CI runner sets this) → "no gates" becomes a hard failure
gates_run=0
skipped=()
skip() { skipped+=("$1"); }
# A gate either produces a number that passes, or it blocks. There is no third state.
gate() { local label="$1"; shift; if "$@"; then gates_run=$((gates_run+1)); echo "  ✓ $label"; else fail "$label"; fi; }

# 1. Graph freshness — built in-agent (/graphify .), not here. Warn only; `make graph-check` is the gate.
gate_graph() {
  [ -f graphify-out/graph.json ] || { echo "::notice::no graphify-out/graph.json — build in-agent with '/graphify .' for the dependency gate"; return 0; }
  [ -f graphify-out/.stale ] && echo "::warning::graph is stale — run '/graphify . --update' in-agent"
  return 0
}

# 2. JS/TS. `npm test` is a TEST gate, not a coverage gate — only a coverage script counts as coverage.
gate_js_coverage() {
  if have npm && grep -q '"coverage"' "$1/package.json" 2>/dev/null; then
    gate "coverage ≥ $COV% (npm run coverage)" run npm --prefix "$1" run coverage
  else skip "coverage JS (no 'coverage' script in $1/package.json — npm test alone measures nothing)"; fi
}

gate_js_mutation() {
  if have npx && ls "$1"/stryker.conf.* "$1"/stryker.config.* >/dev/null 2>&1; then
    gate "mutation ≥ $(threshold mutation 70)% (stryker)" bash -c "cd '$1' && npx stryker run"
  else skip "mutation (no stryker config)"; fi
}

gate_js() {
  local d="$1"
  echo "▶ stack: JS/TS ($d)"
  have npm && gate "tests (npm)" run npm --prefix "$d" test || skip "tests (no npm)"
  gate_js_coverage "$d"
  have madge && gate "dependency cycles = 0 (madge)" run madge --circular "$d" || skip "cycles (no madge)"
  gate_js_mutation "$d"
}

# 3. Python. pytest without pytest-cov measures NO coverage — say so instead of implying it.
gate_python() {
  echo "▶ stack: Python"
  have pytest || { skip "tests/coverage (no pytest)"; return 0; }
  if python3 -c 'import pytest_cov' >/dev/null 2>&1; then
    gate "tests + coverage ≥ $COV% (pytest-cov)" run pytest --cov --cov-fail-under="$COV"
  else
    gate "tests (pytest)" run pytest
    skip "coverage Python (no pytest-cov — pytest alone measures nothing)"
  fi
  have lizard && gate "complexity ≤ $CCN / size ≤ $LEN (lizard)" run lizard -C "$CCN" -L "$LEN" . || skip "complexity Python (no lizard)"
  have mutmut && gate "mutation ≥ $(threshold mutation 70)% (mutmut)" run mutmut run || skip "mutation (no mutmut)"
}

# 4. Shell — lizard/radon can't parse bash, so the framework's own language gets its own gate.
gate_shell() {
  local n; n="$(git ls-files '*.sh' 2>/dev/null | wc -l | tr -d ' ')"
  [ "$n" -gt 0 ] || return 0
  echo "▶ stack: shell ($n files)"
  gate "complexity (shell, CCN ≤ $CCN / body ≤ $(threshold 'shell body' 20))" "$ADF/hooks/shell-complexity.sh"
}

# 5. Evals — the outer loop. A regressed case and an unevaluated change both block the merge.
gate_evals() {
  [ -d "$ADF/docs/evals/fixtures" ] || { skip "evals (no fixtures)"; return 0; }
  echo "▶ evals (Evaluation-Driven Development)"
  gate "eval cases resolved" "$ADF/hooks/eval-agent-flow.sh" --all
  gate "eval coverage of changed behaviour" "$ADF/hooks/eval-required.sh"
}

# 6. Framework contracts — every self-test must pass. Not counted as a stack gate: contracts
# prove the framework works, they say nothing about the code being shipped.
gate_contracts() {
  local t status=0
  for t in "$ADF"/hooks/test-*.sh; do
    [ -f "$t" ] || continue
    bash "$t" >/dev/null || fail "contract: $(basename "$t")"
  done
  echo "  ✓ contracts: $(ls "$ADF"/hooks/test-*.sh 2>/dev/null | wc -l | tr -d ' ') self-test(s)"
  "${ADF_CONTRACTS_PYTHON:-python3}" "$ADF/hooks/check-host-deployment.py" "$ADF" || status=$?
  if [ "$status" -eq 77 ]; then
    skip "host deployment checks (not installed; package self-tests executed)"
  elif [ "$status" -ne 0 ]; then
    fail "host deployment checks"
  fi
}

detect_and_run() {
  local js_dir=""
  [ -f package.json ] && js_dir=.
  [ -z "$js_dir" ] && [ -f sandbox/package.json ] && js_dir=sandbox
  [ -n "$js_dir" ] && gate_js "$js_dir"
  # Not elif: a polyglot repo must be gated on every stack it has, not just the first one found.
  if [ -f pyproject.toml ] || [ -f setup.cfg ] || [ -f pytest.ini ] || [ -f setup.py ]; then gate_python; fi
  gate_shell
  gate_evals
  return 0
}

# Honest verdict — never claim green for gates that never ran.
verdict() {
  [ "${#skipped[@]}" -gt 0 ] && printf '  skipped: %s\n' "${skipped[@]}"
  if [ "$gates_run" -eq 0 ]; then
    local msg="no quality gates evaluated (coverage/mutation/complexity/cycles NOT checked)"
    [ -n "$CI" ] && fail "$msg — configure runners for your stack"
    echo "⚠ $msg — local mode, not a pass. Configure your stack in rules/quality-thresholds.md"
    exit 0
  fi
  echo "✓ $gates_run gate(s) green"
}

echo "▶ CI quality gates (thresholds in rules/quality-thresholds.md)"
gate_graph
detect_and_run
have rtk && rtk gain || true            # token efficiency report (informational)
gate_contracts
verdict
