#!/usr/bin/env bash
# Evaluation-Driven Development gate: a changed skill / command / hook must be evaluated.
#
# Coverage is satisfied by ONE of:
#   1. an eval case declaring it   — docs/evals/fixtures/<case>/task.md: `covers: <path>`
#      (a trailing `/` declares a directory; anything else must match exactly)
#   2. a self-test that exercises it — hooks/test-*.sh mentioning the file (a test-*.sh is its own eval)
#   3. an explicit dated waiver    — docs/evals/waivers.md: "- `<path>` — reason (YYYY-MM-DD)"
#
# Nothing is auto-waived: an unevaluated change fails and names itself. No base ref to
# diff against (shallow clone, no origin) = honest skip, never a silent pass.
#
# Usage: eval-required.sh          (BASE=<ref> to override the diff base)
set -uo pipefail

ADF="${ADF:-ai-development-framework}"
EVALS="$ADF/docs/evals"
WAIVERS="$EVALS/waivers.md"

resolve_base() {
  [ -n "${BASE:-}" ] && { echo "$BASE"; return 0; }
  for ref in origin/main origin/master main HEAD^; do
    git rev-parse --verify -q "$ref" >/dev/null 2>&1 && { echo "$ref"; return 0; }
  done
}

# Changed + untracked, restricted to what the framework treats as behaviour.
changed_paths() {
  { git diff --name-only --diff-filter=d "$1"; git ls-files --others --exclude-standard; } 2>/dev/null |
    grep -E "^$ADF/(skills|commands|hooks)/" | sort -u
}

covered_by_eval() {
  local p="$1" c
  for c in $(grep -rhs '^covers:' "$EVALS"/fixtures/*/task.md 2>/dev/null | sed 's/^covers: *//'); do
    [ "$p" = "$c" ] && return 0
    case "$c" in */) case "$p" in "$c"*) return 0 ;; esac ;; esac
  done
  return 1
}

covered_by_selftest() {
  local b; b="$(basename "$1")"
  case "$b" in test-*.sh) return 0 ;; esac
  # Every skill's basename is SKILL.md — match the skill's NAME, or any test would "cover" all of them.
  case "$1" in */skills/*/SKILL.md) b="$(basename "$(dirname "$1")")" ;; esac
  grep -qls -- "$b" "$ADF"/hooks/test-*.sh 2>/dev/null
}

waived() { grep -qs -- "^- \`$1\` — ." "$WAIVERS"; }

classify() {
  covered_by_eval      "$1" && { echo "  ✓ $1 — eval case";  return 0; }
  covered_by_selftest  "$1" && { echo "  ✓ $1 — self-test";  return 0; }
  waived               "$1" && { echo "  ~ $1 — waived ($WAIVERS)"; return 0; }
  echo "  ✗ $1 — no eval, no self-test, no waiver"
  return 1
}

base="$(resolve_base)"
echo "▶ eval-required (Evaluation-Driven Development)"
[ -n "$base" ] || { echo "⚠ no base ref to diff against — eval coverage NOT checked (not a pass)"; exit 0; }

mapfile -t paths < <(changed_paths "$base")
[ "${#paths[@]}" -gt 0 ] && echo "  base=$base · ${#paths[@]} changed behaviour file(s)" \
                         || { echo "  base=$base · no skill/command/hook changed — nothing to evaluate"; exit 0; }

uncovered=0
for p in "${paths[@]}"; do classify "$p" || uncovered=$((uncovered+1)); done

[ "$uncovered" -eq 0 ] || {
  echo "✗ eval-required: $uncovered change(s) without an eval."
  echo "  Add a case (docs/evals/README.md), a hooks/test-*.sh, or a dated waiver in $WAIVERS"
  exit 1
}
echo "✓ eval-required: every changed skill/command/hook is evaluated or explicitly waived"
