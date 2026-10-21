# Cyclomatic complexity analyser for shell, in awk. Driven by hooks/shell-complexity.sh,
# which owns the thresholds; this file owns the counting and nothing else.
#
#   CCN = 1 + (if|elif|while|until|for) + && + || + case branches (;;)
#   Units: each function, plus the file's top-level body as `<main>`.
#   Output: file<TAB>unit<TAB>ccn<TAB>lines
#
# Known ceilings (deliberate — a real bash parser is the upgrade path, not more regex):
#   · a `}` in column 0 closes a function; nested definitions are out of scope
#   · decision keywords inside single-line quoted strings still count (heredoc bodies do not)
function dec(s,   n) {
  n  = gsub(/(^|[;&|(){}[ \t])(if|elif|while|until|for)([ \t(]|$)/, "&", s)
  n += gsub(/&&|\|\|/, "&", s)
  n += gsub(/;;/, "&", s)
  return n
}
function emit(f, u, c, l) { printf "%s\t%s\t%d\t%d\n", f, u, c, l }
# A new file resets every unit AND the heredoc state — an unterminated heredoc in one file
# must never swallow the next one (that would report a whole file as measured-and-green).
FNR == 1 { if (prev != "") emit(prev, "<main>", mccn + 1, mlen); prev = FILENAME; mccn = 0; mlen = 0; infn = 0; heredoc = "" }
# A heredoc body is data (templates, embedded scripts, fixtures) — never control flow.
heredoc { if ($0 ~ ("^[ \t]*" heredoc "[ \t]*$")) heredoc = ""; next }
/^[ \t]*#/ { next }
/<<-?[ \t]*['"]?[A-Za-z_][A-Za-z0-9_]*/ && !/<<</ {
  hd = $0; sub(/^.*<<-?[ \t]*/, "", hd); sub(/^['"]/, "", hd); sub(/['"].*$/, "", hd); sub(/[^A-Za-z0-9_].*$/, "", hd)
  if (hd != "") heredoc = hd
}
!infn && /^[ \t]*(function[ \t]+)?[A-Za-z_][A-Za-z0-9_]*[ \t]*\([ \t]*\)[ \t]*\{/ {
  name = $0; sub(/[ \t]*\(.*/, "", name); sub(/^[ \t]*(function[ \t]+)?/, "", name)
  rest = $0; sub(/^[^{]*\{/, "", rest)
  if (rest ~ /\}/) { emit(FILENAME, name, 1 + dec(rest), 1); next }
  infn = 1; fname = name; fccn = 1 + dec(rest); flen = 1; next
}
infn { if (/^\}/) { emit(FILENAME, fname, fccn, flen); infn = 0; next } fccn += dec($0); flen++; next }
{ mccn += dec($0); mlen++ }
END { if (prev != "") emit(prev, "<main>", mccn + 1, mlen) }
  
