#!/usr/bin/env bash
# Eval diagnose — the macro step of the improvement loop (Fase 4).
# Reads docs/evals/results.csv (the outcomes) + runs/*.trajectory.md (the evidence)
# and asks the only question that matters across many runs: which cases fail, and
# do they REPEAT? Each failing case gets an improvement-proposal stub pointing at
# its evidence. It proposes; a human decides the fix (CLAUDE.md principle 5).
#
#   Nothing is auto-fixed. No LLM in the loop. The CSV is the truth.
#   A case failing in >=2 distinct commits is flagged "recurring".
#   gate=skipped-* is "no signal", NOT a failure (honest, same policy as the gate).
#
# Usage: eval-diagnose.sh          (exit 0 always — it's a report, not a gate)
set -uo pipefail

ADF="ai-development-framework"
CSV="$ADF/docs/evals/results.csv"
TRAJ_DIR="$ADF/docs/evals/runs"
PROP_DIR="$ADF/docs/traces/proposals"

echo "▶ eval-diagnose"
[ -f "$CSV" ] || { echo "✗ no results at $CSV — run 'make eval-agent-flow-all' first"; exit 0; }
WRITE="${ADF_EVAL_WRITE:-1}"
[ "$WRITE" = 0 ] || mkdir -p "$PROP_DIR"

# One pass over the CSV. Columns: date,commit,case,resolved,iterations,est_tokens,gate
# Emit per case: n_fail (failing rows), n_commits (distinct failing commits), last date+commit.
# ponytail: awk over a small CSV; swap for a real store only if cases reach the hundreds.
summary="$(awk -F, 'NR>1 && $3!="" {
    cs=$3; resolved=$4; gate=$7;
    fail = (resolved=="no" || gate=="fail");
    if (gate ~ /^skipped/) { skip[cs]++; seen[cs]=1; next }
    seen[cs]=1;
    if (fail) { nf[cs]++; if (!(cs FS $2 in c)) { c[cs FS $2]=1; nc[cs]++ }; last[cs]=$1" "$2 }
  }
  END { for (k in seen) printf "%s\t%d\t%d\t%d\t%s\n", k, nf[k]+0, nc[k]+0, skip[k]+0, last[k] }' "$CSV" | sort)"

[ -n "$summary" ] || { echo "  (no cases recorded yet)"; exit 0; }

fails=0; recurring=0; proposals=0
while IFS=$'\t' read -r case nf ncommits nskip last; do
  if [ "$nf" -eq 0 ]; then
    [ "$nskip" -gt 0 ] && echo "  ~ $case: no signal ($nskip skipped, runtime absent)" \
                       || echo "  ✓ $case: passing"
    continue
  fi
  fails=$((fails+1))
  tag=""; [ "$ncommits" -ge 2 ] && { tag=" [RECURRING x$ncommits commits]"; recurring=$((recurring+1)); }
  echo "  ✗ $case: $nf failing run(s)$tag → last $last"

  prop="$PROP_DIR/$case.md"
  if [ "$WRITE" = 0 ]; then
    echo "    · proposal suppressed — eval persistence disabled"
    continue
  fi
  if [ -f "$prop" ]; then
    echo "    · proposal exists: $prop (left untouched — human edits are sacred)"
    continue
  fi
  # ponytail: stub only when absent; never clobber a human-written proposal.
  # Upgrade path: refresh a delimited "auto evidence" block if staleness bites.
  traj="$TRAJ_DIR/$case.trajectory.md"; [ -f "$traj" ] || traj="(missing — capture one)"
  { echo "# Improvement proposal — $case";
    echo;
    echo "> Auto-stub from eval-diagnose. Fill the human sections; the eval validates the fix.";
    echo;
    echo "## Evidence";
    echo "- Failing runs: **$nf** across **$ncommits** commit(s)${tag}";
    echo "- Last failure: \`$last\`";
    echo "- Trajectory: \`$traj\`";
    echo "- Gate/results: \`$CSV\` (rows where case=$case, resolved=no|gate=fail)";
    echo;
    echo "## Hypothesis (human)";
    echo "_Why does the agent flow fail this case? Which step — reason, act, or gate reading?_";
    echo;
    echo "## Proposed change (human)";
    echo "_Target ONE of: a skill, a hook, or a prompt. Smallest change that could fix it._";
    echo "- [ ] skill: \`…\`";
    echo "- [ ] hook: \`…\`";
    echo "- [ ] prompt/command: \`…\`";
    echo;
    echo "## Expected impact";
    echo "_Which metric moves, and by how much? (resolved=yes, iterations, est_tokens)_";
    echo;
    echo "## Confidence";
    echo "**$( [ "$ncommits" -ge 2 ] && echo medium || echo low )** — mechanical: $ncommits failing commit(s).";
    echo "Only a human raises this to high, in the PR that applies the change.";
    echo;
    echo "## Validation";
    echo "- [ ] \`make eval-agent-flow CASE=$case\` → resolved=yes after the change";
    echo "- [ ] no regression in other cases (\`make eval-agent-flow-all\`)";
  } > "$prop"
  echo "    → wrote proposal stub: $prop"
  proposals=$((proposals+1))
done <<< "$summary"

echo "▶ $fails failing case(s), $recurring recurring, $proposals new proposal(s) in $PROP_DIR"
exit 0
