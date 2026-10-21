#!/usr/bin/env bash
# Learning loop — recorded failures become improvement proposals. Suggest-only.
#
# Reads the signal that already exists: docs/observability/events.jsonl, where
# ci-quality-gates, the maintenance routines and reviewers record failures.
# Eval-sourced failures belong to eval-diagnose.sh — one writer per signal class,
# so stub logic is never duplicated. Run both via `make learn`.
#
#   Nothing is auto-fixed. No rule, skill or CLAUDE.md is edited here.
#   It proposes; a human decides in a PR (CLAUDE.md principle 5).
#   A task failing on >=2 distinct UTC days is flagged "recurring".
#   Confidence is mechanical: recurring => medium, single => low. Never high.
#
# Usage: learn.sh          (exit 0 always — it's a report, not a gate)
set -uo pipefail

ADF="${ADF:-ai-development-framework}"
EVENTS="$ADF/docs/observability/events.jsonl"
PROP_DIR="$ADF/docs/traces/proposals"

echo "▶ learn (observability signals)"
[ -f "$EVENTS" ] || { echo "  (no events at $EVENTS — nothing recorded yet)"; exit 0; }
mkdir -p "$PROP_DIR"

# One pass over the JSONL. Per failing task: n_fail, distinct days, last timestamp, phases.
# ponytail: awk over an append-only log; swap for a store only if events reach millions.
summary="$(awk '
  function field(line, key,   parts, val) {
    if (split(line, parts, "\"" key "\":\"") < 2) return "";
    split(parts[2], val, "\""); return val[1];
  }
  /"outcome":"failure"/ {
    task = field($0, "task"); if (task == "") next;
    day = substr(field($0, "timestamp"), 1, 10);
    n[task]++;
    if (!((task SUBSEP day) in sd)) { sd[task SUBSEP day] = 1; days[task]++ }
    ph = field($0, "phase");
    if (ph != "" && index(" " phases[task] " ", " " ph " ") == 0) phases[task] = phases[task] " " ph;
    last[task] = field($0, "timestamp");
  }
  END { for (t in n) printf "%s\t%d\t%d\t%s\t%s\n", t, n[t], days[t], last[t], phases[t] }
' "$EVENTS" | sort)"

[ -n "$summary" ] || { echo "  ✓ no failures recorded"; exit 0; }

# What the failure class implies, and where a fix would land. Suggestion only.
target() {
  case "$1" in
    gate-*)    echo "rules/quality-thresholds.md (threshold) or the code that broke the gate" ;;
    routine-*) echo "hooks/maintenance-routine.sh (the routine) or rules/ (the rule it enforces)" ;;
    review-*)  echo "rules/minimalism.md (the ladder) or the reviewed code" ;;
    *)         echo "skills/ (the flow) or CLAUDE.md (a prime directive)" ;;
  esac
}
label() {
  case "$1" in
    gate-*)    echo "quality gate" ;;
    routine-*) echo "maintenance routine" ;;
    review-*)  echo "PonyTail review must-cut" ;;
    *)         echo "agent-flow task" ;;
  esac
}

failing=0; recurring=0; proposals=0; skipped=0
while IFS=$'\t' read -r task nfail ndays last phases; do
  # Never trust a hand-editable log with a filename. Same contract as observability.sh.
  case "$task" in
    [A-Za-z0-9]*) ;;
    *) echo "  ⚠ skipped unsafe task name: '$task'"; skipped=$((skipped+1)); continue ;;
  esac
  case "$task" in
    *[!A-Za-z0-9_.-]*) echo "  ⚠ skipped unsafe task name: '$task'"; skipped=$((skipped+1)); continue ;;
  esac

  failing=$((failing+1))
  tag=""; conf="low"
  if [ "$ndays" -ge 2 ]; then
    tag=" [RECURRING x$ndays days]"; conf="medium"; recurring=$((recurring+1))
  fi
  echo "  ✗ $task ($(label "$task")): $nfail failure(s)$tag → last $last"

  prop="$PROP_DIR/$task.md"
  if [ -f "$prop" ]; then
    echo "    · proposal exists: $prop (left untouched — human edits are sacred)"
    continue
  fi
  { echo "# Improvement proposal — $task";
    echo;
    echo "> Auto-stub from \`make learn\`. Fill the human sections; nothing here is applied automatically.";
    echo;
    echo "## Problem";
    echo "A $(label "$task") kept failing: \`$task\`.${phases:+ Phase(s):$phases}";
    echo;
    echo "## Evidence";
    echo "- Failures: **$nfail** across **$ndays** distinct UTC day(s)${tag}";
    echo "- Last failure: \`$last\`";
    echo "- Source: \`$EVENTS\` (rows where task=$task, outcome=failure)";
    echo;
    echo "## Proposed change (human)";
    echo "_Smallest change that could fix it. Likely target: $(target "$task")._";
    echo "- [ ] rule: \`…\`";
    echo "- [ ] skill: \`…\`";
    echo "- [ ] hook: \`…\`";
    echo "- [ ] prompt/command: \`…\`";
    echo;
    echo "## Expected impact";
    echo "_Which metric moves, and by how much? (gate pass, complexity, mutation, tokens, routine exit)_";
    echo;
    echo "## Confidence";
    echo "**$conf** — mechanical: $( [ "$conf" = medium ] && echo "repeated across $ndays days" || echo "single-day signal, may be noise")."
    echo "Only a human raises this to high, in the PR that applies the change.";
    echo;
    echo "## Validation";
    echo "- [ ] the failing signal stops reappearing in \`make learn\`";
    echo "- [ ] \`make quality\`, \`make skill-audit\`, \`make mcp-audit\`, \`make graph-check\` stay green";
  } > "$prop"
  echo "    → wrote proposal stub: $prop"
  proposals=$((proposals+1))
done <<< "$summary"

sk=""; [ "$skipped" -gt 0 ] && sk=", $skipped skipped"
echo "▶ $failing failing task(s), $recurring recurring, $proposals new proposal(s)$sk in $PROP_DIR"
echo "  next: fill the stubs, then 'make learn-apply' to open a PR (never applied to main)"
exit 0
