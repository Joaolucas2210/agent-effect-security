#!/usr/bin/env bash
# The one reader of rules/quality-thresholds.md. Sourced by the gates — no side effects,
# nothing executed. Keeps the numbers in the table instead of scattered across scripts.
#
#   threshold <lowercase-regex matching the Gate column> <fallback>
#
# The fallback exists so a repo that deleted the table still gets a real gate, never a pass.

ADF="${ADF:-ai-development-framework}"
THRESHOLDS_FILE="${THRESHOLDS_FILE:-$ADF/rules/quality-thresholds.md}"

threshold() {
  local n=""
  [ -f "$THRESHOLDS_FILE" ] &&
    n="$(awk -F'|' -v k="$1" 'tolower($2) ~ k { gsub(/[^0-9]/, "", $4); print $4; exit }' "$THRESHOLDS_FILE")"
  [ -n "$n" ] && printf '%s' "$n" || printf '%s' "$2"
}
