# hooks

| File | Trigger | Does |
|---|---|---|
| `rtk-wrap.sh` | Claude Code PreToolUse(Bash) | reminds/routes commands through RTK |
| `graph-update.sh` | Claude Code PostToolUse(Edit\|Write) | marks graph stale (rebuild in-agent with `/graphify . --update`) |
| `pre-commit` | git pre-commit | cheap local gates (complexity/size) + graph refresh |
| `ci-quality-gates.sh` | CI | full gates: coverage, complexity, mutation, cycles + `rtk gain` |

## Install
```bash
chmod +x hooks/*.sh hooks/pre-commit
ln -sf ../../ai-development-framework/hooks/pre-commit .git/hooks/pre-commit   # from repo root
```
Claude Code hooks (`rtk-wrap.sh`, `graph-update.sh`) are wired in `settings.json`.

> Tool command lines in `ci-quality-gates.sh` are commented — uncomment and match your stack.
> RTK/Graphify commands are best-effort and no-op if the tool is absent.
