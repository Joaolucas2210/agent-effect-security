# INC-01: Rules File Backdoor (Cursor, GitHub Copilot)

- **Date / source:** 2025-03 · Pillar Security
- **Threat:** THR-02 · **Legs:** 2 · **OWASP:** ASI01, ASI05
- **Status:** out_of_scope → covered after ADR 0028 · **Eval:** `eval-inc-01` (red)

## Vector

Hidden Unicode (zero-width, bidi) inside `.cursor/rules` / Copilot instruction files makes the agent emit
backdoored code while the rules look benign in review. The file arrives through a PR, a template or a shared repo.

## Lesson

Instruction files are untrusted *executable* input, not documentation. Review of rendered text is not review.

## ADF

Today: the file is read as any workspace file (tainted); nothing stops the agent from *writing* it.
After ADR 0028: writes to `.cursor/`, `.claude/`, `CLAUDE.md`, `AGENTS.md` are denied with
`uncovered_write_denied_agent_config`; reads stay tainted. Not covered: a rules file already in the repo
before ADF (that is review, not runtime).
