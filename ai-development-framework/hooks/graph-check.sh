#!/usr/bin/env bash
# Knowledge-graph freshness gate.
#
# The graph indexes CODE TOPOLOGY. A commit that only touches docs/config (or files graphify
# parses no topology from, e.g. shell) does not stale it — but graphify only re-stamps
# GRAPH_REPORT.md on a topology change, so its "Built from commit" line lags behind HEAD on
# topology-neutral commits. Comparing stamp == HEAD alone therefore reports a false STALE.
#
# Fresh when: stamp == HEAD, OR stamp is an ancestor of HEAD (graph was built from a commit in
#   HEAD's history; when graphify is present it is re-run first, so any real code drift rebuilds
#   and re-stamps to HEAD, and the pre-commit hook does the same on every commit).
#   OR (squash merge) the stamp is a commit main never contains, its object still exists, and
#   stamp..HEAD changes no code (DOC_ONLY paths only); the stamp is then re-stamped to HEAD.
# Stale when: stamp is not in HEAD's history and code changed since (or the stamp object is gone).
#
# Env: GRAPH_REPORT overrides the report path; GRAPH_CHECK_NO_REFRESH=1 skips `graphify update`.
set -uo pipefail

read_stamp() { grep -oE 'Built from commit: `[0-9a-f]{7,40}`' "$1" | grep -oE '[0-9a-f]{7,40}' | head -1; }

# graphify is the authority on topology drift: re-run it so real code changes rebuild + re-stamp.
# No-op (no writes) when the graph already matches the code. Skipped for CI / custom reports.
refresh() {
  [ -z "${GRAPH_CHECK_NO_REFRESH:-}" ] && [ "$1" = "graphify-out/GRAPH_REPORT.md" ] && command -v graphify >/dev/null 2>&1 || return 0
  graphify update >/dev/null 2>&1 || true
}

# Squash merges rewrite the branch commits, so the stamp is never in main's history even when the
# code is identical. Fresh when the stamp object still exists and stamp..HEAD changes no code; then
# re-stamp to HEAD (unless read-only) so the next check passes on ancestry even after git gc.
squash_fresh() {
  local report="$1" built="$2" head="$3"
  git cat-file -e "$built^{commit}" 2>/dev/null || return 1
  git diff --name-only "$built" HEAD | grep -qvE "$DOC_ONLY" && return 1
  if [ -n "${GRAPH_CHECK_NO_REFRESH:-}" ]; then
    echo "✓ graph fresh (built at $built, squash-merged: no code change since; read-only, not re-stamped)"
    return 0
  fi
  restamp "$report" "$built" "$(git rev-parse HEAD)"
  echo "✓ graph fresh (built at $built, squash-merged: no code change since; re-stamped to $head)"
}

check() {
  # Resolve per-call (not at load) so GRAPH_REPORT overrides work when check() is called in-process.
  local report="${GRAPH_REPORT:-graphify-out/GRAPH_REPORT.md}" built head
  [ -f "$report" ] || { echo "✗ graph-check: $report missing — build in-agent with /graphify ."; return 1; }
  refresh "$report"
  built=$(read_stamp "$report")
  [ -n "$built" ] || { echo "✗ graph-check: no 'Built from commit' line in $report"; return 1; }
  head=$(git rev-parse --short="${#built}" HEAD 2>/dev/null) || { echo "✗ graph-check: not a git repo"; return 1; }
  if [ "$built" = "$head" ]; then echo "✓ graph fresh (commit $head)"; return 0; fi
  if git merge-base --is-ancestor "$built" HEAD 2>/dev/null; then
    echo "✓ graph fresh (built at $built, an ancestor of HEAD $head — no code-topology drift since; stamp lags only on topology-neutral commits)"
    return 0
  fi
  squash_fresh "$report" "$built" "$head" && return 0
  echo "✗ graph STALE: built from $built, not in HEAD ($head) history — run /graphify . to rebuild"
  return 1
}

# Paths graphify extracts no code topology from. Conservative: anything else (incl. .json/.yml) is code.
DOC_ONLY='\.(md|txt|png|jpe?g|gif|svg|pdf|csv)$|(^|/)(LICENSE|VERSION)$'

# Rewrite only the freshness stamp, in the report and (best effort) in graph.json.
restamp() {
  local report="$1" old="$2" new="$3" graph
  sed -i.bak "s/Built from commit: \`$old\`/Built from commit: \`${new:0:8}\`/" "$report" && rm -f "$report.bak"
  graph="$(dirname "$report")/graph.json"
  [ -f "$graph" ] && command -v python3 >/dev/null 2>&1 && python3 - "$graph" "$new" <<'PY' || true
import json, sys
path, commit = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding="utf-8")); data["built_at_commit"] = commit
open(path, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False))
PY
}

expect() { if [ "$1" = "$2" ]; then echo "✓ $3"; else echo "✗ $3 (got $2)"; fi; }
stamp_of() { grep -oE '[0-9a-f]{7,40}' "$1"; }
write_stamp() { printf 'Built from commit: `%s`\n' "$2" > "$1"; }

# Ancestry tolerance, on this repo's real history.
ancestry_cases() {
  local tmp; tmp=$(mktemp)
  write_stamp "$tmp" "$(git rev-parse --short "HEAD~1" 2>/dev/null || git rev-parse --short HEAD)"
  GRAPH_REPORT="$tmp" GRAPH_CHECK_NO_REFRESH=1 check >/dev/null; expect 0 $? "ancestor stamp → fresh"
  write_stamp "$tmp" deadbeef
  GRAPH_REPORT="$tmp" GRAPH_CHECK_NO_REFRESH=1 check >/dev/null; expect 1 $? "non-ancestor stamp → stale"
  rm -f "$tmp"
}

# Throwaway repo: main, then a feature branch (code commit, docs commit) squash-merged into main.
# Prints the stamp a graph built on the feature's code commit would carry.
squash_fixture() (
  set -e
  cd "$1"
  git init -q; git config user.email g@example.invalid; git config user.name g
  echo 'a = 1' > app.py; git add app.py; git commit -qm base; git branch -q -M main
  git checkout -qb feature; echo 'b = 2' >> app.py; git commit -qam code
  echo doc > notes.md; git add notes.md; git commit -qm docs
  git rev-parse --short HEAD~1
  git checkout -q main; git merge -q --squash feature >/dev/null; git commit -qm squash
)

# Squash merge: the stamp is a branch commit main never contains, with the same code.
squash_cases() {
  local repo stamp report
  repo=$(mktemp -d); report="$repo/report.md"
  stamp=$(squash_fixture "$repo") || { echo "✗ squash fixture failed"; return 1; }
  cd "$repo" || return 1
  write_stamp "$report" "$stamp"; GRAPH_REPORT="$report" check >/dev/null; expect 0 $? "squash stamp, docs-only drift → fresh"
  expect "$(git rev-parse --short=8 HEAD)" "$(stamp_of "$report")" "squash stamp re-stamped to HEAD"
  write_stamp "$report" "$stamp"; GRAPH_REPORT="$report" GRAPH_CHECK_NO_REFRESH=1 check >/dev/null; expect 0 $? "read-only mode still fresh"
  expect "$stamp" "$(stamp_of "$report")" "read-only mode never re-stamps"
  echo 'c = 3' >> app.py; git commit -qam more-code
  write_stamp "$report" "$stamp"; GRAPH_REPORT="$report" check >/dev/null; expect 1 $? "squash stamp, code drift → stale"
  write_stamp "$report" 000000000000; GRAPH_REPORT="$report" check >/dev/null; expect 1 $? "unknown stamp object → stale"
  cd - >/dev/null; rm -rf "$repo"
}

# ONE runnable check for the non-trivial logic: fake reports, real git history.
self_test() {
  local out; out=$( ancestry_cases; (squash_cases) )
  echo "$out"
  echo "self-test: $(grep -c '^✓' <<<"$out") passed, $(grep -c '^✗' <<<"$out") failed"
  ! grep -q '^✗' <<<"$out"
}

case "${1:-}" in
  --self-test) self_test ;;
  *)           check ;;
esac
