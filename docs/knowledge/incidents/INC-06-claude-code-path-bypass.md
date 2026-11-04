# INC-06: Claude Code path restriction bypass and command injection ⚠

- **Date / source:** 2025-08 · Cymulate · CVE-2025-54794, CVE-2025-54795 ⚠ (verify ids)
- **Threat:** THR-01 · **Legs:** 1 · **OWASP:** ASI02
- **Status:** covered (`Read` edge) · **Eval:** `eval-inc-06` (to add: prefix-match variants)

## Vector

Prefix-based path check (`/home/u/project` also matched `/home/u/project-evil`) let reads escape the
workspace; a second flaw allowed shell command injection through crafted tool arguments.

## Lesson

Path normalisation is a security boundary: lexical prefix checks, symlinks and `..` must be handled at the
open, not at the string.

## ADF

Covered for `Read`: the gate makes the path relative lexically, `..` and absolute paths are contract denies,
the runtime opens component-by-component with `dir_fd` + `O_NOFOLLOW` inside a detached worktree, and
`fstat` on the handle validates the target. Eval to add: `project-evil` sibling directory, symlink to
outside, `..` after normalisation. Not covered: the same bypass through `Bash`.
