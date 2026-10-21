#!/usr/bin/env bash
# skill-audit.sh self-check: hard failures must stay hard, warnings must stay advisory.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
audit() { ( cd "$ROOT/.." && "$ROOT/hooks/skill-audit.sh" "$tmp/skills" 2>&1 ); }
skill() { mkdir -p "$tmp/skills/$1"; printf -- '---\nname: %s\ndescription: %s\n---\n\n%s\n' "$2" "$3" "${4:-}" > "$tmp/skills/$1/SKILL.md"; }

# valid: frontmatter matches the directory, refs resolve, "when not to use" present
skill good good "does one thing" "Use hooks/learn.sh. When NOT to use: never."
audit | grep -q '✓ skill-audit passed'

# missing name/description, dir mismatch, broken ref — each a hard failure
skill mismatch other "wrong name in frontmatter"
audit >/dev/null && { echo "✗ accepted name != directory" >&2; exit 1; }
rm -rf "$tmp/skills/mismatch"

skill broken broken "points at nothing" "See hooks/does-not-exist.sh"
out="$(audit)" && { echo "✗ accepted a broken ref" >&2; exit 1; }
grep -q "broken ref 'hooks/does-not-exist.sh'" <<< "$out"
rm -rf "$tmp/skills/broken"

mkdir -p "$tmp/skills/empty"
audit >/dev/null && { echo "✗ accepted a skill with no SKILL.md" >&2; exit 1; }
rm -rf "$tmp/skills/empty"

# a ref truncated at a glob is a pattern, not a broken path
skill globby globby "mentions a family of files" "Run hooks/test-*.sh and rules/<name>.md"
audit | grep -q '✓ skill-audit passed'
rm -rf "$tmp/skills/globby"

# advisory only: no 'when NOT to use' warns but must not block
skill terse terse "no guidance about when to skip it"
out="$(audit)"; grep -q "⚠ terse: no 'when NOT to use'" <<< "$out"; grep -q '✓ skill-audit passed' <<< "$out"

echo "✓ skill-audit self-test"
