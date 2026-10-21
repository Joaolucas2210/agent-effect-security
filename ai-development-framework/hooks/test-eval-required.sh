#!/usr/bin/env bash
# eval-required.sh self-check: the Evaluation-Driven Development gate.
# Invariants: an unevaluated change blocks; a waiver must carry a reason; no base = skip, not pass.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
fw="$tmp/fw"
mkdir -p "$fw/hooks" "$fw/skills/demo" "$fw/docs/evals/fixtures/case-a"
( cd "$tmp" && git init -q . && git config user.email t@t && git config user.name t \
    && git commit -q --allow-empty -m base )
gate() { ( cd "$tmp" && ADF=fw BASE="${BASE:-HEAD}" "$ROOT/hooks/eval-required.sh" 2>&1 ); }

# 1. A new hook with nothing evaluating it blocks, and names itself.
echo 'echo hi' > "$fw/hooks/new-thing.sh"
out="$(gate)" && { echo "✗ unevaluated change passed" >&2; exit 1; }
grep -q 'hooks/new-thing.sh — no eval, no self-test, no waiver' <<< "$out"

# 2. An eval case that declares it covers the file satisfies the gate.
printf 'covers: fw/hooks/new-thing.sh\n' > "$fw/docs/evals/fixtures/case-a/task.md"
gate | grep '✓ eval-required' >/dev/null
grep -q 'new-thing.sh — eval case' <<< "$(gate)"

# 3. A directory declaration needs the trailing slash; a bare prefix must NOT match.
printf 'covers: fw/hooks\n' > "$fw/docs/evals/fixtures/case-a/task.md"
gate >/dev/null && { echo "✗ a bare prefix was treated as a directory" >&2; exit 1; }
printf 'covers: fw/hooks/\n' > "$fw/docs/evals/fixtures/case-a/task.md"
gate | grep '✓ eval-required' >/dev/null

# 4. A self-test that mentions the file covers it; a test-*.sh is its own eval.
rm "$fw/docs/evals/fixtures/case-a/task.md"
echo '# exercises new-thing.sh' > "$fw/hooks/test-new-thing.sh"
out="$(gate)"; grep -q 'new-thing.sh — self-test' <<< "$out"
grep -q 'test-new-thing.sh — self-test' <<< "$out"

# 4b. A skill is matched by its NAME, not by the shared "SKILL.md" basename.
echo '# mentions SKILL.md and new-thing.sh' > "$fw/hooks/test-new-thing.sh"
printf -- '---\nname: demo\n---\n' > "$fw/skills/demo/SKILL.md"
gate >/dev/null && { echo "✗ SKILL.md basename passed as coverage" >&2; exit 1; }
grep -q 'skills/demo/SKILL.md — no eval' <<< "$(gate)"

# 5. A waiver needs a reason; the bare path is not a waiver.
rm "$fw/hooks/test-new-thing.sh" "$fw/skills/demo/SKILL.md"
printf '# Waivers\n\n- `fw/hooks/new-thing.sh`\n' > "$fw/docs/evals/waivers.md"
gate >/dev/null && { echo "✗ a reasonless waiver passed" >&2; exit 1; }
printf '# Waivers\n\n- `fw/hooks/new-thing.sh` — wrapper only (2026-08-21)\n' > "$fw/docs/evals/waivers.md"
gate | grep '~ fw/hooks/new-thing.sh — waived' >/dev/null

# 6. Docs and code outside skills/commands/hooks are not behaviour — no ceremony for them.
rm "$fw/docs/evals/waivers.md" "$fw/hooks/new-thing.sh"
mkdir -p "$fw/docs"; echo 'notes' > "$fw/docs/notes.md"
gate | grep 'nothing to evaluate' >/dev/null

# 7. No base ref to diff against: honest skip, explicitly not a pass.
empty="$tmp/empty"; mkdir -p "$empty/fw"; ( cd "$empty" && git init -q . )
out="$( cd "$empty" && ADF=fw BASE="" "$ROOT/hooks/eval-required.sh" )"
grep -q 'NOT checked (not a pass)' <<< "$out"

echo "✓ eval-required self-test"
