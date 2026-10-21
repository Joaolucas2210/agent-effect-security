#!/usr/bin/env bash
# Skill governance audit — every framework skill must be valid, self-describing, non-redundant.
# HARD (exit 1): no SKILL.md, missing name/description, name != dir, broken internal file ref.
# WARN (advisory): oversize, missing "when NOT to use", description keyword overlap.
# Usage: skill-audit.sh [SKILLS_DIR]   (default: ai-development-framework/skills)
# Contract & deprecation policy: ai-development-framework/docs/skill-governance.md
set -uo pipefail

ADF="${ADF:-ai-development-framework}"
dir="${1:-$ADF/skills}"
MAX_LINES=80

fails=0; warns=0; count=0
descs="$(mktemp)"; trap 'rm -f "$descs"' EXIT

# One skill = one unit. HARD checks first, then advisory. Increments the shared counters.
audit_skill() {
  local sk="$1" name_dir f fm_name desc lines
  name_dir="$(basename "$sk")"
  f="$sk/SKILL.md"
  [ -f "$f" ] || { echo "✗ $name_dir: no SKILL.md"; fails=$((fails+1)); return 0; }

  fm_name="$(awk -F': *' '/^name:/{print $2; exit}' "$f")"
  desc="$(awk '/^description:/{sub(/^description: */,""); print; exit}' "$f")"
  lines="$(wc -l <"$f")"

  [ -n "$fm_name" ] || { echo "✗ $name_dir: missing 'name:' in frontmatter"; fails=$((fails+1)); }
  [ -n "$desc" ]    || { echo "✗ $name_dir: missing 'description:' in frontmatter"; fails=$((fails+1)); }
  [ -z "$fm_name" ] || [ "$fm_name" = "$name_dir" ] || { echo "✗ $name_dir: name '$fm_name' != directory"; fails=$((fails+1)); }

  audit_refs "$name_dir" "$f"

  [ "$lines" -le "$MAX_LINES" ] || { echo "⚠ $name_dir: $lines lines (> $MAX_LINES) — consider trimming"; warns=$((warns+1)); }
  grep -qiE 'when not|not to use|nao usar|não usar|skip (this|when)|avoid when' "$f" \
    || { echo "⚠ $name_dir: no 'when NOT to use' guidance (mandatory metadata — ratcheting)"; warns=$((warns+1)); }

  printf '%s\t%s\n' "$name_dir" "$desc" >> "$descs"
}

# broken internal refs — framework-internal source prefixes only. Example paths in code blocks
# don't match; generated artifacts (graphify-out/, *.log) are excluded — presence varies.
audit_refs() {
  local name_dir="$1" f="$2" ref
  while IFS= read -r ref; do
    [ -n "$ref" ] || continue
    # A ref truncated at a glob/placeholder (`hooks/test-*.sh`, `rules/<name>`) is a pattern,
    # not a path — the capture stops at the wildcard, leaving a trailing `-` or `/`.
    case "$ref" in *.log|*-|*/) continue;; esac
    [ -e "$ADF/$ref" ] || [ -e "$ref" ] || { echo "✗ $name_dir: broken ref '$ref'"; fails=$((fails+1)); }
  done < <(grep -oE '(hooks|rules|agents|skills|docs)/[a-zA-Z0-9_./-]+|(CLAUDE|AGENTS)\.md' "$f" | sed 's/[.,)]*$//' | sort -u)
}

echo "▶ skill-audit ($dir)"
for sk in "$dir"/*/; do
  [ -d "$sk" ] || continue
  count=$((count+1))
  audit_skill "$sk"
done

# Ponytail ladder must not drift: rules/ is what .cursorrules loads (no skills/ there),
# skills/ponytail is what the Claude Code Skill tool loads. Two loaders, one wording.
ladder() { grep -E '^[0-9]+\. ' "$1"; }
lad_a="$ADF/rules/minimalism.md"; lad_b="$ADF/skills/ponytail/SKILL.md"
if [ -f "$lad_a" ] && [ -f "$lad_b" ] && ! diff -q <(ladder "$lad_a") <(ladder "$lad_b") >/dev/null; then
  echo "✗ ponytail ladder drift: $lad_a != $lad_b"; fails=$((fails+1))
fi

# keyword overlap across descriptions (advisory redundancy signal)
overlap="$(awk -F'\t' '
BEGIN{split("metric metrics quality graph review skill skills before after tokens token output codebase should minimal",a," "); for(k in a) stop[a[k]]=1}
{ n=split(tolower($2), w, /[^a-z]+/);
  for(i=1;i<=n;i++){ x=w[i]; if(length(x)<5||(x in stop)) continue;
    if(!(x SUBSEP $1 in seen)){seen[x SUBSEP $1]=1; cnt[x]++; who[x]=who[x]" "$1} } }
END{ for(x in cnt) if(cnt[x]>=4) printf "⚠ overlap: \"%s\" in %d skills:%s\n", x, cnt[x], who[x] }
' "$descs")"
if [ -n "$overlap" ]; then echo "$overlap"; warns=$((warns + $(printf '%s\n' "$overlap" | grep -c .))); fi

echo
echo "skills: $count · hard fails: $fails · warnings: $warns"
[ "$fails" -eq 0 ] || { echo "✗ skill-audit: $fails hard failure(s)"; exit 1; }
echo "✓ skill-audit passed ($warns warning(s) — see docs/skill-governance.md)"
