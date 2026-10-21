#!/usr/bin/env bash
# Cyclomatic complexity + function length gate for SHELL.
# Why it exists: lizard/radon don't parse bash, so this framework's own language
# (15 hooks, ~1.2k lines) was the one thing the complexity gate never measured.
# No new dependency — awk counts decision points; thresholds come from
# rules/quality-thresholds.md so there is one source of truth for the numbers.
#
#   CCN = 1 + (if|elif|while|until|for) + && + || + case branches (;;)
#   Units = each function, plus the top-level body as `<main>`.
#   Exit 1 on any unit over threshold. The number is the gate.
#
# Usage: shell-complexity.sh [--report] [path...]     (default: all tracked *.sh + hooks/pre-commit)
set -uo pipefail

ADF="${ADF:-ai-development-framework}"
# shellcheck source=thresholds.sh
. "$(dirname "${BASH_SOURCE[0]}")/thresholds.sh"
MAXCCN="$(threshold complexity 10)"     # functions — same number as every other language
MAXBODY="$(threshold 'shell body' 20)" # script top-level — declared, ratcheting (see the rules file)
MAXLEN="$(threshold size 50)"

report=0; [ "${1:-}" = "--report" ] && { report=1; shift; }
if [ "$#" -gt 0 ]; then files=("$@"); else
  mapfile -t files < <(git ls-files '*.sh' 'hooks/pre-commit' "$ADF/hooks/pre-commit" 2>/dev/null)
fi
[ "${#files[@]}" -gt 0 ] || { echo "⚠ shell-complexity: no shell files to measure"; exit 0; }

echo "▶ shell-complexity (fn CCN ≤ $MAXCCN, fn length ≤ $MAXLEN, script body CCN ≤ $MAXBODY) — ${#files[@]} file(s)"

# The counting lives in shell-complexity.awk (different language, own file).
AWK_SRC="$(dirname "${BASH_SOURCE[0]}")/shell-complexity.awk"
# A missing analyser must be a loud failure: measuring nothing would report "all green".
[ -f "$AWK_SRC" ] || { echo "✗ shell-complexity: analyser missing ($AWK_SRC) — nothing was measured"; exit 1; }
measure() { awk -f "$AWK_SRC" "$@"; }

# The length gate is a *function* rule; a long linear script body is not a 50-line function.
violations="$(measure "${files[@]}" | awk -F'\t' -v mc="$MAXCCN" -v mb="$MAXBODY" -v ml="$MAXLEN" '
  $2 == "<main>" { if ($3 > mb) printf "  ✗ %s:%s script-body CCN %d > %d — extract functions\n", $1, $2, $3, mb; next }
  $3 > mc { printf "  ✗ %s:%s CCN %d > %d\n", $1, $2, $3, mc }
  $4 > ml { printf "  ✗ %s:%s length %d > %d lines\n", $1, $2, $4, ml }')"
worst="$(measure "${files[@]}" | sort -t$'\t' -k3,3nr | head -3 |
  awk -F'\t' '{printf "    %s:%s CCN=%d len=%d\n", $1, $2, $3, $4}')"

[ "$report" -eq 1 ] && { measure "${files[@]}" | sort -t$'\t' -k3,3nr | awk -F'\t' '{printf "%-52s %-28s CCN=%-3d len=%d\n", $1, $2, $3, $4}'; exit 0; }
if [ -n "$violations" ]; then
  echo "$violations"; echo "✗ shell-complexity: over threshold — extract functions (Uncle Bob: the number is the gate)"; exit 1
fi
echo "  worst offenders (still green):"; echo "$worst"
echo "✓ shell-complexity: ${#files[@]} file(s) within fn CCN ≤ $MAXCCN, fn length ≤ $MAXLEN, body CCN ≤ $MAXBODY"
