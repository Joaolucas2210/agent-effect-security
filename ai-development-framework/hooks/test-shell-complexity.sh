#!/usr/bin/env bash
# shell-complexity.sh self-check: the counter, both thresholds, file attribution,
# and the invariant that the numbers come from the rules table — not the script.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$ROOT/hooks/shell-complexity.sh"   # counting lives in hooks/shell-complexity.awk
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

# A table the gate must obey (deliberately different numbers than the defaults).
cat > "$tmp/thresholds.md" <<'MD'
| Gate | Metric | Default | Rationale |
|---|---|---|---|
| Complexity | cyclomatic / fn | ≤ 3 | test |
| Shell body | cyclomatic / script top-level | ≤ 4 | test |
| Size | fn length | ≤ 5 lines | test |
MD
gate() { THRESHOLDS_FILE="$tmp/thresholds.md" "$GATE" "$@" 2>&1; }

# One decision per construct: if, elif, while, until, for, &&, ||, and each case branch.
case_counter() {
  cat > "$tmp/simple.sh" <<'FIXTURE'
simple() {
  [ -f x ] && echo ok
}
simple
FIXTURE
  gate "$tmp/simple.sh" | grep -q '✓ shell-complexity'

  cat > "$tmp/busy.sh" <<'FIXTURE'
busy() {
  if a; then b; elif c; then d; fi
  while e; do f; done
  for g in 1 2; do h; done
  i && j || k
}
busy
FIXTURE
  out="$(gate "$tmp/busy.sh" || true)"
  grep -q 'busy CCN 7 > 3' <<< "$out"   # 1 + if + elif + while + for + && + || = 7

  cat > "$tmp/pick.sh" <<'FIXTURE'
pick() {
  case "$1" in a) x ;; b) y ;; *) z ;; esac
}
pick x
FIXTURE
  grep -q 'pick CCN 4 > 3' <<< "$(gate "$tmp/pick.sh" || true)"

  # comments never count, and a one-line function is still a unit
  cat > "$tmp/comment.sh" <<'FIXTURE'
# if a && b || c
noop() { :; }
noop
FIXTURE
  gate "$tmp/comment.sh" | grep -q '✓ shell-complexity'
}

# Length is a FUNCTION rule; a long linear script body is not a 50-line function violation.
case_length() {
  { echo 'longfn() {'; for i in $(seq 1 8); do echo "  echo $i"; done; echo '}'; echo 'longfn'; } > "$tmp/long.sh"
  grep -q 'longfn length 9 > 5' <<< "$(gate "$tmp/long.sh" || true)"   # signature line + 8 body lines
  { for i in $(seq 1 30); do echo "echo $i"; done; } > "$tmp/linear.sh"
  gate "$tmp/linear.sh" | grep -q '✓ shell-complexity'
}

# A script body has its own declared threshold and its own message.
case_body() {
  cat > "$tmp/body.sh" <<'FIXTURE'
a && b
c && d
e && f
g && h
FIXTURE
  grep -q 'body.sh:<main> script-body CCN 5 > 4' <<< "$(gate "$tmp/body.sh" || true)"
}

# Regression guard: <main> must be attributed to its OWN file, not to the next one measured.
case_attribution() {
  out="$(gate --report "$tmp/simple.sh" "$tmp/body.sh")"
  grep -q "$tmp/body.sh .*<main> .*CCN=5" <<< "$out"
  grep -q "$tmp/simple.sh .*<main> .*CCN=1" <<< "$out"   # its only branch lives in the function
}

# A heredoc body is data: these fixture scripts must not inflate this file's own numbers.
# Heredoc bodies are data, and their state must not leak between files or out of comments.
case_heredoc() {
  cat > "$tmp/hd.sh" <<'FIXTURE'
emit() {
  cat <<'INNER'
if a; then b; elif c; then d; fi
i && j || k
INNER
}
# a commented heredoc must start nothing: cat <<GHOST
a && b
FIXTURE
  gate "$tmp/hd.sh" | grep -q '✓ shell-complexity'          # embedded text counted nothing
  grep -q 'hd.sh .*<main> .*CCN=2' <<< "$(gate --report "$tmp/hd.sh")"   # only the real `a && b`

  # An unterminated heredoc must not swallow the NEXT file measured.
  printf 'runaway() {\n  cat <<NEVERENDS\n  text\n}\n' > "$tmp/runaway.sh"
  grep -q 'body.sh:<main> script-body CCN 5 > 4' <<< "$(gate "$tmp/runaway.sh" "$tmp/body.sh" || true)"
}

case_counter
case_length
case_body
case_attribution
case_heredoc
gate --report "$tmp/busy.sh" >/dev/null          # --report never gates

# A missing analyser measures nothing — which must read as failure, never as "all green".
cp "$GATE" "$tmp/orphan.sh"
out="$("$tmp/orphan.sh" "$tmp/simple.sh" 2>&1)" && { echo "✗ passed with no analyser" >&2; exit 1; }
grep -q 'analyser missing' <<< "$out"

( cd "$ROOT/.." && "$GATE" >/dev/null )          # the framework's own shell passes its own gate

echo "✓ shell-complexity self-test"
