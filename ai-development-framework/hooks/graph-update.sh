#!/usr/bin/env bash
# PostToolUse(Edit|Write) hook: flag the knowledge graph as stale after a file change.
# The graph is built by the /graphify skill in-agent (LLM-driven) — a shell hook CANNOT
# build it. So we just drop a marker; the agent rebuilds with `/graphify . --update`.
# ponytail: marker + hint, not a fake build command.
set -euo pipefail
[ "${GRAPHIFY_AUTO_UPDATE:-1}" = "1" ] || exit 0
[ -f graphify-out/graph.json ] || exit 0   # no graph yet → nothing to mark stale
touch graphify-out/.stale 2>/dev/null || true
echo "graphify: graph marked stale — refresh in-agent with '/graphify . --update'"
exit 0
