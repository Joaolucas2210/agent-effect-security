# INC-06: Claude Code path restriction bypass and command injection

- **Date / source:** 2025-08 · Cymulate (Elad Beber) · CVE-2025-54794 (path restriction bypass, fixed in 0.2.111; GHSA-pmw4-pwvc-3hx2) and CVE-2025-54795 (command injection, CWE-78, fixed in 1.0.20; GHSA-x56v-x2h6-7j34) — verified 2026-11-04
- **Threat:** THR-01 · **Legs:** 1 · **OWASP:** ASI02
- **Status:** covered (`Read` edge) · **Eval:** `eval-inc-06` (to add: prefix-match variants)

## Vector

A flaw in file-path validation let reads escape the intended directory (community write-ups describe a
string-prefix check: `/home/u/project` also matching `/home/u/project-evil`; not confirmed by the advisory); a
second flaw in command parsing bypassed the confirmation prompt and ran an untrusted command.

## Lesson

Path normalisation is a security boundary: lexical prefix checks, symlinks and `..` must be handled at the
open, not at the string.

## ADF

Covered for `Read`: the gate makes the path relative lexically, `..` and absolute paths are contract denies,
the runtime opens component-by-component with `dir_fd` + `O_NOFOLLOW` inside a detached worktree, and
`fstat` on the handle validates the target. Eval to add: `project-evil` sibling directory, symlink to
outside, `..` after normalisation. Not covered: the same bypass through `Bash`.
