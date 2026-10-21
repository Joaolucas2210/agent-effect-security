#!/usr/bin/env bash
# PreToolUse(Bash) hook: nudge commands through RTK for compressed output.
# ponytail: advisory only — emits a reminder, does not rewrite the command
# (Claude Code's hook auto-rewrite already handles the real routing). Upgrade to
# active rewriting only if the auto-rewrite is unavailable in your setup.
set -euo pipefail
command -v rtk >/dev/null 2>&1 || { echo "rtk not found — install RTK (see skills/rtk-integration)"; exit 0; }
echo "RTK active: run dev/metric commands as 'rtk <cmd>' to keep output compressed."
exit 0
